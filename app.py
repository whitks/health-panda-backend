from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_restful import Api, Resource
from flask_jwt_extended import (
    jwt_required,
    create_access_token,
    JWTManager,
    get_jwt_identity,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from flask_cors import CORS
import os
import uuid
from werkzeug.utils import secure_filename

# Optional HuggingFace imports (initialized lazily)
try:
    from transformers import pipeline
    import torch
    HF_AVAILABLE = True
except Exception:
    HF_AVAILABLE = False

# -----------------------------
# APP CONFIG
# -----------------------------
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///project.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = "supersecret"

CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})

db = SQLAlchemy(app)
api = Api(app)
jwt = JWTManager(app)

# -----------------------------
# DATABASE MODELS
# -----------------------------
class User(db.Model):
    __tablename__ = "user"

    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    created_on = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc)
    )

    profile = db.relationship(
        "UserProfile",
        backref="user",
        uselist=False,
        cascade="all, delete",
    )

    def set_password(self, raw_password):
        self.password = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password, raw_password)


class UserProfile(db.Model):
    __tablename__ = "user_profile"

    profile_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.user_id"),
        nullable=False,
    )

    weight = db.Column(db.Float, nullable=False)
    height = db.Column(db.Float, nullable=False)
    body_type = db.Column(db.String(30), nullable=False)
    fitness_goal = db.Column(db.String(50), nullable=False)
    activity_level = db.Column(db.String(50), nullable=False)

    created_on = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_on = db.Column(
        db.DateTime,
        onupdate=lambda: datetime.now(timezone.utc),
    )


# -----------------------------
# FOOD ENTRY MODEL + UPLOADS
# -----------------------------

# Upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


class FoodEntry(db.Model):
    __tablename__ = "food_entry"

    entry_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.user_id"), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    food_name = db.Column(db.String(150), nullable=False)
    calories = db.Column(db.Float, nullable=True)
    confidence = db.Column(db.Float, nullable=True)
    created_on = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# -----------------------------
# PREDICTION / NUTRITION HELPERS
# -----------------------------


def predict_food(image_path):
    """
    Predict food using a Hugging Face image-classification model if available,
    otherwise fall back to a filename heuristic.

    Returns dict: {food_name, calories, confidence}
    """
    # Local calorie lookup for some common foods
    FOOD_CALORIES = {
        "apple": 95.0,
        "banana": 105.0,
        "pizza": 285.0,
        "sandwich": 250.0,
        "salad": 150.0,
        "burger": 354.0,
        "rice": 206.0,
        "egg": 78.0,
    }

    # Use HF model when available
    if HF_AVAILABLE:
        global _hf_clf
        try:
            _hf_clf
        except NameError:
            device = 0 if ("torch" in globals() and torch.cuda.is_available()) else -1
            # model: community Food-101 fine-tuned model
            try:
                _hf_clf = pipeline("image-classification", model="nateraw/food-101-resnet50", device=device)
            except Exception:
                # If model download fails, disable HF for fallback
                try:
                    del _hf_clf
                except Exception:
                    pass
                return _predict_by_filename(image_path, FOOD_CALORIES)

        try:
            preds = _hf_clf(image_path, top_k=3)
            # choose the top label
            top = preds[0]
            label = top.get("label") if isinstance(top, dict) else str(top)
            score = float(top.get("score", 0.0))
            # normalize label (Food-101 labels are typically clean)
            label_key = label.split(",")[0].lower()
            calories = FOOD_CALORIES.get(label_key)
            return {"food_name": label_key, "calories": calories, "confidence": score}
        except Exception:
            return _predict_by_filename(image_path, FOOD_CALORIES)

    # fallback: filename heuristic
    return _predict_by_filename(image_path, FOOD_CALORIES)


def _predict_by_filename(image_path, FOOD_CALORIES):
    fname = os.path.basename(image_path).lower()
    for key in FOOD_CALORIES.keys():
        if key in fname:
            return {"food_name": key, "calories": FOOD_CALORIES[key], "confidence": 0.5}
    return {"food_name": "unknown", "calories": None, "confidence": 0.0}


# -----------------------------
# API RESOURCES
# -----------------------------

# Register
class Register(Resource):
    def post(self):
        data = request.get_json()
        # Only create the user account here. Profile fields are handled
        # separately via the protected profile endpoint.
        if User.query.filter_by(email=data["email"]).first():
            return {"message": "Email already exists"}, 400

        new_user = User(
            name=data.get("name"),
            email=data.get("email"),
        )
        new_user.set_password(data.get("password"))

        db.session.add(new_user)
        db.session.commit()

        return {"message": "User registered successfully"}, 201


# Login
class Login(Resource):
    def post(self):
        data = request.get_json()

        user = User.query.filter_by(email=data["email"]).first()

        if not user or not user.check_password(data["password"]):
            return {"message": "Invalid credentials"}, 401

        access_token = create_access_token(identity=user.user_id)
        # JWT subjects should be strings for some jwt libraries/versions.
        access_token = create_access_token(identity=str(user.user_id))

        return {"access_token": access_token}, 200


# Get Profile (Protected)
class Profile(Resource):
    @jwt_required()
    def get(self):
        # get_jwt_identity() returns the subject (we encoded user_id as a string)
        try:
            current_user_id = int(get_jwt_identity())
        except (TypeError, ValueError):
            return {"message": "Invalid token subject"}, 422
        profile = UserProfile.query.filter_by(
            user_id=current_user_id
        ).first()

        if not profile:
            return {"message": "Profile not found"}, 404

        return {
            "weight": profile.weight,
            "height": profile.height,
            "body_type": profile.body_type,
            "fitness_goal": profile.fitness_goal,
            "activity_level": profile.activity_level,
        }, 200

    @jwt_required()
    def post(self):
        """Create or update the current user's profile.

        Expected JSON: weight, height, body_type, fitness_goal, activity_level
        """
        data = request.get_json() or {}
        try:
            current_user_id = int(get_jwt_identity())
        except (TypeError, ValueError):
            return {"message": "Invalid token subject"}, 422

        profile = UserProfile.query.filter_by(user_id=current_user_id).first()

        # Validate minimal fields
        required = ["weight", "height", "body_type", "fitness_goal", "activity_level"]
        missing = [f for f in required if f not in data]
        if missing:
            return {"message": f"Missing fields: {', '.join(missing)}"}, 400

        if profile:
            profile.weight = data["weight"]
            profile.height = data["height"]
            profile.body_type = data["body_type"]
            profile.fitness_goal = data["fitness_goal"]
            profile.activity_level = data["activity_level"]
            db.session.commit()
            return {"message": "Profile updated"}, 200

        # create new profile
        new_profile = UserProfile(
            user_id=current_user_id,
            weight=data["weight"],
            height=data["height"],
            body_type=data["body_type"],
            fitness_goal=data["fitness_goal"],
            activity_level=data["activity_level"],
        )
        db.session.add(new_profile)
        db.session.commit()
        return {"message": "Profile created"}, 201


# -----------------------------
# FOOD RESOURCE
# -----------------------------
class Food(Resource):
    @jwt_required()
    def post(self):
        """Accepts multipart/form-data with key 'image'."""
        current_identity = get_jwt_identity()
        try:
            current_user_id = int(current_identity)
        except (TypeError, ValueError):
            return {"message": "Invalid token subject"}, 422

        if "image" not in request.files:
            return {"message": "No image file provided"}, 400
        file = request.files["image"]
        if file.filename == "" or not allowed_file(file.filename):
            return {"message": "Invalid or missing image file"}, 400

        filename = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        file.save(save_path)

        # Predict and store
        result = predict_food(save_path)
        food_name = result.get("food_name", "unknown")
        calories = result.get("calories")
        confidence = result.get("confidence", 0.0)

        entry = FoodEntry(
            user_id=current_user_id,
            image_path=save_path,
            food_name=food_name,
            calories=calories,
            confidence=confidence,
        )
        db.session.add(entry)
        db.session.commit()

        return {
            "entry_id": entry.entry_id,
            "food_name": food_name,
            "calories": calories,
            "confidence": confidence,
        }, 201

    @jwt_required()
    def get(self):
        current_identity = get_jwt_identity()
        try:
            current_user_id = int(current_identity)
        except (TypeError, ValueError):
            return {"message": "Invalid token subject"}, 422

        entries = (
            FoodEntry.query.filter_by(user_id=current_user_id)
            .order_by(FoodEntry.created_on.desc())
            .all()
        )
        out = []
        for e in entries:
            out.append(
                {
                    "entry_id": e.entry_id,
                    "food_name": e.food_name,
                    "calories": e.calories,
                    "confidence": e.confidence,
                    "image_path": e.image_path,
                    "created_on": e.created_on.isoformat(),
                }
            )
        return {"entries": out}, 200


# -----------------------------
# ROUTES
# -----------------------------
api.add_resource(Register, "/api/register")
api.add_resource(Login, "/api/login")
api.add_resource(Profile, "/api/profile")
api.add_resource(Food, "/api/food")


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)




































    