from app import create_app
import os

app = create_app()

if __name__ == '__main__':
    # Bỏ kích hoạt hardcoded debug=True theo yêu cầu fix security
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode)
