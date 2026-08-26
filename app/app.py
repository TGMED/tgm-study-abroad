from dotenv import load_dotenv

load_dotenv()

from flask import Flask  # noqa: E402

from extensions import close_db, get_or_create_secret_key, init_db  # noqa: E402
from blueprints.roi import roi_bp  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.chat import chat_bp  # noqa: E402
from blueprints.community import community_bp  # noqa: E402
from blueprints.social import social_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402


def create_app():
    app = Flask(__name__)
    app.secret_key = get_or_create_secret_key()
    # Don't let browsers cache CSS/JS during active development, so UI
    # changes (toasts, styles, scripts) show up on a normal refresh.
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    close_db(app)

    app.register_blueprint(roi_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(admin_bp)

    return app


app = create_app()
init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
