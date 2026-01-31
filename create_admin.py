from app import app, db
from models import User

def create_admin():
    with app.app_context():
        # Check if user exists
        if db.session.query(User).filter_by(username='admin').first():
            print("User 'admin' already exists.")
            return

        user = User(username='admin', email='admin@example.com', is_admin=True)
        user.set_password('admin')
        db.session.add(user)
        db.session.commit()
        print("Created user 'admin' with password 'admin'")

if __name__ == "__main__":
    create_admin()
