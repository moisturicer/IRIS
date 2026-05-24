# Local Setup Guide

Step-by-step instructions to run IRIS locally and access the dashboard with test accounts for each role.

**Prerequisites:** Python 3.11+, Node.js 18+, PostgreSQL 14+, Redis (optional — only needed for Celery/email tasks).

---

## Step 1 — Database

Run in **psql** or the **pgAdmin** query tool:

```sql
CREATE USER iris_user WITH PASSWORD 'iris_password';
CREATE DATABASE iris_db OWNER iris_user;
GRANT ALL PRIVILEGES ON DATABASE iris_db TO iris_user;
```

> **Docker alternative:** from the repo root, run `docker compose up db -d` to start PostgreSQL with matching credentials.

---

## Step 2 — Backend setup

```bash
cd C:\Users\leeja\Desktop\IRIS\backend
venv\Scripts\activate
pip install -r requirements/development.txt
```

Make sure `.env` exists at `backend/.env` with:

```properties
SECRET_KEY=your-generated-secret-key
DEBUG=True
DB_NAME=iris_db
DB_USER=iris_user
DB_PASSWORD=iris_password
DB_HOST=localhost
DB_PORT=5432
FRONTEND_URL=http://localhost:5173
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=30
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7
AXES_FAILURE_LIMIT=3
```

> Save the file to disk before running Django commands. An unsaved editor buffer will cause `SECRET_KEY not found` errors.

---

## Step 3 — Migrate and create superuser

```bash
python manage.py migrate
python manage.py createsuperuser
```

---

## Step 4 — Verify and assign admin role

Replace `YOUR_USERNAME` with the username you chose in `createsuperuser`:

```bash
python manage.py shell -c "from apps.accounts.models import User; u = User.objects.get(username='YOUR_USERNAME'); u.is_verified = True; u.save(); print(u.username, u.is_verified)"
```

Then open the Django shell:

```bash
python manage.py shell
```

Paste this to seed roles and assign the admin role:

```python
from apps.accounts.models import User, Role

roles = ["Student", "Adviser", "KTTO", "RDCO", "ITSO", "TBI", "IERC", "System Administrator"]
for name in roles:
    Role.objects.get_or_create(name=name)

admin_role = Role.objects.get(name="System Administrator")
u = User.objects.get(username="YOUR_USERNAME")
u.role = admin_role
u.is_verified = True
u.save()
print(u.username, u.role.name)
```

---

## Step 5 — Seed test accounts for all roles

Still inside the shell, paste this:

```python
from apps.accounts.models import User, Role

test_users = [
    ("test_student", "student@iris.dev", "Student"),
    ("test_adviser", "adviser@iris.dev", "Adviser"),
    ("test_ktto", "ktto@iris.dev", "KTTO"),
    ("test_rdco", "rdco@iris.dev", "RDCO"),
    ("test_itso", "itso@iris.dev", "ITSO"),
    ("test_ierc", "ierc@iris.dev", "IERC"),
]

for username, email, role_name in test_users:
    role = Role.objects.get(name=role_name)
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"email": email, "first_name": "Test", "last_name": role_name},
    )
    user.email = email
    user.set_password("testpass123")
    user.role = role
    user.is_verified = True
    user.save()
    print(f"{'Created' if created else 'Updated'}: {username} → {role_name}")

exit()
```

---

## Step 6 — Start the backend

```bash
python manage.py runserver
```

Backend runs at **http://localhost:8000**.

---

## Step 7 — Frontend (new terminal)

```bash
cd C:\Users\leeja\Desktop\IRIS\frontend
npm install
npm run dev
```

Frontend runs at **http://localhost:5173**.

> Run `npm run dev` from the `frontend/` folder, not the repo root.

---

## Step 8 — Login

Go to **http://localhost:5173/login** and sign in with **email, not username**:

| Account      | Email                    | Password      | Landing page       |
|--------------|--------------------------|---------------|--------------------|
| Your admin   | email from createsuperuser | your password | `/admin/users`     |
| Test student | `student@iris.dev`       | `testpass123` | `/`                |
| Test adviser | `adviser@iris.dev`       | `testpass123` | `/review/pending`  |
| Test KTTO    | `ktto@iris.dev`          | `testpass123` | `/review/pending`  |
| Test RDCO    | `rdco@iris.dev`          | `testpass123` | `/review/pending`  |
| Test ITSO    | `itso@iris.dev`          | `testpass123` | `/records`         |
| Test IERC    | `ierc@iris.dev`          | `testpass123` | `/review/pending`  |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `SECRET_KEY not found` | Save `backend/.env` to disk |
| `Email not verified` | Run Step 4 verify command |
| 403 — Access Denied after login | Assign a role in Step 4 |
| Database connection error | Confirm PostgreSQL is running and `DB_*` values match |
| API errors in browser | Ensure backend (`:8000`) and frontend (`:5173`) are both running |

---

## Optional — Celery worker

Email verification and background tasks require Celery. In a separate terminal:

```bash
cd C:\Users\leeja\Desktop\IRIS\backend
venv\Scripts\activate
celery -A config worker -l info
```

If you skip this step, sign-up emails will not be sent, but login and dashboard access work normally when accounts are marked verified manually.
