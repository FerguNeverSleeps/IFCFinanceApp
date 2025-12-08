# IFCFinanceApp - Linux Setup Guide

## Prerequisites

*   **Python 3.12+**
*   **Docker & Docker Compose** (for the local database, to avoid having to connect to the default suprabase database during development)

## Installation

1.  **Create a Virtual Environment**:
    It is recommended to use a virtual environment to manage dependencies.
    ```bash
    python3 -m venv .ifc-venv
    source venv/bin/activate
    ```

2.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd IFCFinanceApp
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Database Setup

This application uses a PostgreSQL database. A `docker-compose.yml` file is provided to run a local instance easily.

1.  **Start the Database**:
    ```bash
    docker compose up -d
    ```
    *Note: The database runs on port **5440** to avoid conflicts with default Postgres installations.*

2.  **Initialize the Database**:
    If this is your first time running the app, apply the migrations to create the database schema:
    ```bash
    flask db upgrade
    ```

    If, later, changes are made to the database models, generate a new migration and apply it:
    ```bash
    flask db migrate -m "Description of changes"
    flask db upgrade
    ```

3.  **Create an Admin User**:
    To create a default admin user (`admin` / `admin`), run the helper script:
    ```bash
    python create_admin.py
    ```

> Note: If you ever take down the database in a way that clears it (e.g. taking down with volumes (-v) or pruning your images) you will need to reapply the migrations and recreate the admin user.

## Running the Application

1.  **Start the Flask Server**:
    ```bash
    python app.py
    ```

2.  **Access the App**:
    Open your browser and navigate to:
    [http://localhost:5000](http://localhost:5000)

## Configuration

The application is configured to connect to the local Docker database by default.

To connect to a different database (e.g., a production Supabase instance), set the `DATABASE_URL` environment variable:

```bash
export DATABASE_URL="postgresql://user:password@host:port/dbname"
python app.py
```

## Database Migrations (Reiterated)

If you modify the database models in `models.py`, generate a new migration:

```bash
flask db migrate -m "Description of changes"
flask db upgrade
```
