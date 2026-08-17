from flask import Flask, jsonify

from config import Config
from app.extensions import db, jwt, cors, bcrypt


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}}, supports_credentials=True)

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
    from app.routes.vendors import bp as vendors_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.misc import bp as misc_bp

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
    app.register_blueprint(vendors_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(misc_bp)

    # Serve uploaded files (resumes, generated job-post images)
    from flask import send_from_directory

    @app.get("/static/uploads/<path:filepath>")
    def uploaded_file(filepath):
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
        return jsonify({"message": "Something went wrong on our end. Please try again."}), 500

    return app
