
from flask import Flask, jsonify
import os

from config import Config
from app.extensions import db, jwt, cors, bcrypt


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )

    from app.models import User

    # Immediately revoke access for removed or deactivated users.
    @jwt.token_in_blocklist_loader
    def _account_no_longer_active(_jwt_header, jwt_payload):
        if jwt_payload.get("type") != "access":
            return False

        user = db.session.get(User, int(jwt_payload["sub"]))
        return user is None or not user.is_active

    @jwt.revoked_token_loader
    def _revoked_response(_jwt_header, _jwt_payload):
        return jsonify({"message": "This account is no longer active."}), 401

    from app.routes.auth import bp as auth_bp
    from app.routes.employees import bp as employees_bp
    from app.routes.attendance import bp as attendance_bp
    from app.routes.leave import bp as leave_bp
    from app.routes.payroll import bp as payroll_bp
    from app.routes.recruitment import bp as recruitment_bp
    from app.routes.screening import bp as screening_bp
    from app.routes.mocktest import bp as mocktest_bp
    from app.routes.offers import bp as offers_bp
    from app.routes.documents import bp as documents_bp
    from app.routes.employee_profile import bp as employee_profile_bp
    from app.routes.insurance import bp as insurance_bp
    from app.routes.vendors import bp as vendors_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.misc import bp as misc_bp
    from app.routes.notifications import bp as notifications_bp
    from app.routes.exports import bp as exports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(leave_bp)
    app.register_blueprint(payroll_bp)
    app.register_blueprint(recruitment_bp)
    app.register_blueprint(screening_bp)
    app.register_blueprint(mocktest_bp)
    app.register_blueprint(offers_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(employee_profile_bp)
    app.register_blueprint(insurance_bp)
    app.register_blueprint(vendors_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(exports_bp)

    # Serve public uploaded files while blocking protected document paths.
    from flask import send_from_directory

    @app.get("/static/uploads/<path:filepath>")
    def uploaded_file(filepath):
        normalized_path = os.path.normpath(
            filepath.replace("/", os.sep).replace("\\", os.sep)
        )
        normalized_path = normalized_path.replace("\\", "/").casefold()
        path_parts = normalized_path.split("/")

        # Employee documents require authenticated access.
        if normalized_path.startswith("documents/"):
            return jsonify({
                "message": "Employee documents require authenticated access."
            }), 404

        # Vendor agreement PDFs must not be served through this public route.
        if "vendor_agreements" in path_parts:
            return jsonify({"message": "Resource not found."}), 404

        return send_from_directory(app.config["UPLOAD_FOLDER"], filepath)

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "service": app.config["COMPANY_NAME"],
                "powered_by": app.config["POWERED_BY"],
            }
        )

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"message": "Resource not found."}), 404

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify({
            "message": "Something went wrong on our end. Please try again."
        }), 500

    return app
