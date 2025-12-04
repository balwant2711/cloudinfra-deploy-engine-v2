import os
from datetime import datetime
import zipfile
from werkzeug.utils import secure_filename
import threading
import time
import json

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)
from flask_sqlalchemy import SQLAlchemy
from functools import wraps

from utils.terraform_runner import (run_terraform_template_job,run_terraform_custom_job,run_terraform_destroy_job)
# -------------------------
# Flask App Setup
# -------------------------

app = Flask(__name__)

# Secret key for sessions (change this in real project)
app.config["SECRET_KEY"] = "super-secret-key-change-this"

# SQLite DB config
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "cloudinfra.db")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + DB_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

CUSTOM_JOBS_DIR = os.path.join(BASE_DIR, "..", "custom_jobs")
os.makedirs(CUSTOM_JOBS_DIR, exist_ok=True)

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

db = SQLAlchemy(app)

# -------------------------
# Database Models
# -------------------------

class User(db.Model):
    """
    Very simple user model for now.
    Future: proper password hashing + registration system.
    """
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)  # plain for now (NOT for production)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Job(db.Model):
    """
    Deployment Job model – template/custom mode, status, logs path etc.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    mode = db.Column(db.String(20), nullable=False)  # "template" / "custom"
    template_name = db.Column(db.String(100), nullable=True)

    status = db.Column(db.String(20), default="Pending")  # Pending / Queued / Running / Success / Failed / Destroyed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    log_file_path = db.Column(db.String(255), nullable=True)

    # NEW: store full terraform outputs as JSON string
    outputs_json = db.Column(db.Text, nullable=True)

    # NEW: a single main output to quickly show on dashboard
    primary_output = db.Column(db.String(255), nullable=True)


def run_template_job_async(job_id, template_id, tf_vars, aws_access_key, aws_secret_key, aws_region):


    with app.app_context():
        job = Job.query.get(job_id)
        if not job:
            return

        job.status = "Running"
        db.session.commit()

        success, log_file_path, outputs = run_terraform_template_job(
            job_id=job.id,
            template_name=template_id,
            variables=tf_vars,
            aws_access_key=aws_access_key,
            aws_secret_key=aws_secret_key,
            aws_region=aws_region,
            base_dir=BASE_DIR,
            logs_dir=LOGS_DIR,
        )

        job.log_file_path = log_file_path
        job.finished_at = datetime.utcnow()
        job.status = "Success" if success else "Failed"

        if outputs:
            job.outputs_json = json.dumps(outputs)

            # Primary output selection per template
            if template_id == "web_server":
                ip = outputs.get("instance_public_ip", {}).get("value")
                dns = outputs.get("instance_public_dns", {}).get("value")
                job.primary_output = dns or ip

            elif template_id == "vpc_basic":
                vpc_id = outputs.get("vpc_id", {}).get("value")
                job.primary_output = vpc_id

            elif template_id == "s3_cloudfront":
                cf_domain = outputs.get("cloudfront_domain_name", {}).get("value")
                site_endpoint = outputs.get("website_endpoint", {}).get("value")
                job.primary_output = cf_domain or site_endpoint

            elif template_id == "two_tier_app":
                web_dns = outputs.get("web_public_dns", {}).get("value")
                web_ip = outputs.get("web_public_ip", {}).get("value")
                job.primary_output = web_dns or web_ip

            elif template_id == "eks_basic":
                endpoint = outputs.get("cluster_endpoint", {}).get("value")
                name = outputs.get("cluster_name", {}).get("value")
                job.primary_output = endpoint or name

            elif template_id == "alb_asg":
                alb_dns = outputs.get("alb_dns_name", {}).get("value")
                job.primary_output = alb_dns

            elif template_id == "secure_web_hosting":
                ip = outputs.get("instance_public_ip", {}).get("value")
                dns = outputs.get("instance_public_dns", {}).get("value")
                job.primary_output = dns or ip

        db.session.commit()


def run_custom_job_async(job_id, zip_path, aws_access_key, aws_secret_key, aws_region):
    with app.app_context():
        job = Job.query.get(job_id)
        if not job:
            return

        job.status = "Running"
        db.session.commit()

        success, log_file_path, outputs = run_terraform_custom_job(
            job_id=job.id,
            zip_file_path=zip_path,
            custom_jobs_root=CUSTOM_JOBS_DIR,
            aws_access_key=aws_access_key,
            aws_secret_key=aws_secret_key,
            aws_region=aws_region,
            logs_dir=LOGS_DIR,
        )

        job.log_file_path = log_file_path if isinstance(log_file_path, str) else None
        job.finished_at = datetime.utcnow()
        job.status = "Success" if success else "Failed"

        if outputs:
            job.outputs_json = json.dumps(outputs)

            # For generic custom projects, we don't know which is main,
            # but we can pick the first key's value as primary_output
            try:
                first_key = next(iter(outputs))
                val = outputs[first_key].get("value")
                job.primary_output = str(val)
            except Exception:
                pass

        db.session.commit()

# -------------------------
# Helper: Login Required Decorator
# -------------------------

from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# -------------------------
# Initial DB + Default User
# -------------------------

with app.app_context():
    db.create_all()

    existing = User.query.filter_by(email="admin@example.com").first()
    if not existing:
        user = User(email="admin@example.com", password="admin123")
        db.session.add(user)
        db.session.commit()
# -------------------------
# Routes
# -------------------------

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Very basic login using fixed user in DB.
    Future: add registration and password hashing.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(email=email).first()

        if user and user.password == password:
            session["user_id"] = user.id
            session["user_email"] = user.email
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get("user_id")
    jobs = Job.query.filter_by(user_id=user_id).order_by(Job.created_at.desc()).all()
    return render_template("dashboard.html", jobs=jobs)

@app.route("/jobs/<int:job_id>/logs")
@login_required
def view_job_logs(job_id):
    """
    Display the log contents for a specific job.
    """
    user_id = session.get("user_id")
    job = Job.query.filter_by(id=job_id, user_id=user_id).first()

    if not job:
        flash("Job not found or you don't have access.", "danger")
        return redirect(url_for("dashboard"))

    log_content = ""
    if job.log_file_path and os.path.isfile(job.log_file_path):
        with open(job.log_file_path, "r", encoding="utf-8") as f:
            log_content = f.read()
    else:
        log_content = "No log file found for this job."

    return render_template("logs.html", job=job, log_content=log_content)

@app.route("/jobs/<int:job_id>/logs/stream")
@login_required
def stream_job_logs(job_id):
    """
    Returns the latest content of a job's log file.
    Used by frontend JS for live log updates.
    """
    user_id = session.get("user_id")
    job = Job.query.filter_by(id=job_id, user_id=user_id).first()

    if not job:
        return "Job not found or unauthorized.", 404

    if not job.log_file_path or not os.path.isfile(job.log_file_path):
        # Log file might not be created yet
        return "", 200

    try:
        with open(job.log_file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        content = "Error reading log file."

    # plain text response (easy for frontend)
    return content, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/jobs/<int:job_id>/destroy", methods=["POST"])
@login_required
def destroy_job(job_id):
    user_id = session.get("user_id")
    job = Job.query.filter_by(id=job_id, user_id=user_id).first()

    if not job:
        flash("Job not found or unauthorized access.", "danger")
        return redirect(url_for("dashboard"))

    # Read AWS credentials from form
    aws_access_key = request.form.get("aws_access_key", "").strip()
    aws_secret_key = request.form.get("aws_secret_key", "").strip()
    aws_region = request.form.get("aws_region", "ap-south-1").strip()

    if not aws_access_key or not aws_secret_key:
        flash("AWS credentials are required for destroy action.", "danger")
        return redirect(url_for("dashboard"))

    # Run destroy
    success, log_file_path = run_terraform_destroy_job(
        job_id=job.id,
        job_mode=job.mode,
        template_name=job.template_name,
        custom_jobs_root=CUSTOM_JOBS_DIR,
        base_dir=BASE_DIR,
        logs_dir=LOGS_DIR,
        aws_access_key=aws_access_key,
        aws_secret_key=aws_secret_key,
        aws_region=aws_region,
    )

    # Update job fields
    job.finished_at = datetime.utcnow()
    job.log_file_path = log_file_path
    job.status = "Destroyed" if success else "Destroy Failed"
    db.session.commit()

    if success:
        flash(f"Destroy successful for Job #{job.id}", "success")
    else:
        flash(f"Destroy FAILED for Job #{job.id}. Check logs.", "danger")

    return redirect(url_for("dashboard"))

@app.route("/jobs/<int:job_id>/outputs")
@login_required
def view_job_outputs(job_id):
    user_id = session.get("user_id")
    job = Job.query.filter_by(id=job_id, user_id=user_id).first()

    if not job:
        flash("Job not found or unauthorized.", "danger")
        return redirect(url_for("dashboard"))

    outputs = {}
    if job.outputs_json:
        try:
            outputs = json.loads(job.outputs_json)
        except Exception:
            outputs = {}

    return render_template("outputs.html", job=job, outputs=outputs)

# Placeholder routes for next steps
@app.route("/deploy/template", methods=["GET", "POST"])
@login_required
def deploy_template():
    """
    Template Mode:
    - Supports multiple templates (web_server, vpc_basic, s3_cloudfront)
    - Each template requires a different set of variables
    """

    available_templates = [
        {"id": "web_server", "label": "Web Server – Single EC2 Instance"},
        {"id": "vpc_basic", "label": "VPC – Public/Private Subnets"},
        {"id": "s3_cloudfront", "label": "Static Website – S3 + CloudFront"},
        {"id": "two_tier_app", "label": "Two-Tier App – EC2 + RDS"},
        {"id": "eks_basic", "label": "EKS Cluster – Basic Managed Node Group"},
        {"id": "alb_asg", "label": "ALB + ASG – Highly Available Web App"},
        {"id": "secure_web_hosting", "label": "Secure Web Hosting – Hardened EC2 Web Server"},
    ]

    if request.method == "POST":
        template_id = request.form.get("template_id")

        # Common fields
        aws_access_key = request.form.get("aws_access_key", "").strip()
        aws_secret_key = request.form.get("aws_secret_key", "").strip()
        aws_region = request.form.get("aws_region", "").strip() or "ap-south-1"

        if not template_id:
            flash("Please select a template.", "danger")
            return render_template("deploy_template.html", templates=available_templates)

        if not aws_access_key or not aws_secret_key:
            flash("AWS credentials are required.", "danger")
            return render_template("deploy_template.html", templates=available_templates)

        # Collect template specific fields
        instance_name = request.form.get("instance_name", "").strip()
        key_pair_name = request.form.get("key_pair_name", "").strip()

        vpc_cidr = request.form.get("vpc_cidr", "").strip()
        public_subnet_1_cidr = request.form.get("public_subnet_1_cidr", "").strip()
        public_subnet_2_cidr = request.form.get("public_subnet_2_cidr", "").strip()
        private_subnet_1_cidr = request.form.get("private_subnet_1_cidr", "").strip()
        private_subnet_2_cidr = request.form.get("private_subnet_2_cidr", "").strip()

        s3_bucket_name = request.form.get("s3_bucket_name", "").strip()

        tf_vars = {}

        # Per-template validation + mapping
        if template_id == "web_server":
            if not instance_name or not key_pair_name:
                flash("Instance name and key pair are required for Web Server template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            tf_vars = {
                "instance_name": instance_name,
                "key_pair_name": key_pair_name,
                "aws_region": aws_region,
            }

        elif template_id == "vpc_basic":
            required_vpc_fields = [
                vpc_cidr,
                public_subnet_1_cidr,
                public_subnet_2_cidr,
                private_subnet_1_cidr,
                private_subnet_2_cidr,
            ]
            if not all(required_vpc_fields):
                flash("All VPC and subnet CIDRs are required for VPC template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            tf_vars = {
                "aws_region": aws_region,
                "vpc_cidr": vpc_cidr,
                "public_subnet_1_cidr": public_subnet_1_cidr,
                "public_subnet_2_cidr": public_subnet_2_cidr,
                "private_subnet_1_cidr": private_subnet_1_cidr,
                "private_subnet_2_cidr": private_subnet_2_cidr,
            }

        elif template_id == "s3_cloudfront":
            if not s3_bucket_name:
                flash("Bucket name is required for S3 + CloudFront template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            tf_vars = {
                "aws_region": aws_region,
                "bucket_name": s3_bucket_name,
            }

        elif template_id == "two_tier_app":
            if not instance_name or not key_pair_name:
                flash("Instance name and key pair are required for Two-Tier App template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            db_name = request.form.get("db_name", "").strip()
            db_username = request.form.get("db_username", "").strip()
            db_password = request.form.get("db_password", "").strip()

            if not db_name or not db_username or not db_password:
                flash("DB name, username, and password are required for Two-Tier App template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            tf_vars = {
                "aws_region": aws_region,
                "instance_name": instance_name,
                "key_pair_name": key_pair_name,
                "db_name": db_name,
                "db_username": db_username,
                "db_password": db_password,
            }
        elif template_id == "eks_basic":
            cluster_name = request.form.get("eks_cluster_name", "").strip()
            node_instance_type = request.form.get("eks_node_instance_type", "").strip()
            desired_size = request.form.get("eks_desired_size", "").strip()
            min_size = request.form.get("eks_min_size", "").strip()
            max_size = request.form.get("eks_max_size", "").strip()

            if not cluster_name:
                flash("Cluster name is required for EKS template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            if not node_instance_type:
                node_instance_type = "t3.small"

            # Basic check for scaling numbers
            if not (desired_size and min_size and max_size):
                flash("Desired, min, and max node counts are required for EKS template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            try:
                desired_size = int(desired_size)
                min_size = int(min_size)
                max_size = int(max_size)
            except ValueError:
                flash("EKS node sizes must be integers.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            tf_vars = {
                "aws_region": aws_region,
                "cluster_name": cluster_name,
                "node_instance_type": node_instance_type,
                "desired_size": desired_size,
                "min_size": min_size,
                "max_size": max_size,
            }
        elif template_id == "alb_asg":
            # Reuse instance_name + key_pair_name fields
            if not instance_name or not key_pair_name:
                flash("Instance name and key pair are required for ALB + ASG template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            asg_instance_type = request.form.get("asg_instance_type", "").strip() or "t2.micro"
            asg_desired = request.form.get("asg_desired_capacity", "").strip()
            asg_min = request.form.get("asg_min_size", "").strip()
            asg_max = request.form.get("asg_max_size", "").strip()

            if not (asg_desired and asg_min and asg_max):
                flash("ASG desired, min, and max sizes are required for ALB + ASG template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            try:
                asg_desired = int(asg_desired)
                asg_min = int(asg_min)
                asg_max = int(asg_max)
            except ValueError:
                flash("ASG sizes must be integers.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            tf_vars = {
                "aws_region": aws_region,
                "instance_name": instance_name,
                "key_pair_name": key_pair_name,
                "asg_instance_type": asg_instance_type,
                "asg_desired_capacity": asg_desired,
                "asg_min_size": asg_min,
                "asg_max_size": asg_max,
            }

        elif template_id == "secure_web_hosting":
            if not instance_name or not key_pair_name:
                flash("Instance name and key pair are required for Secure Web Hosting template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            allowed_ssh_cidr = request.form.get("allowed_ssh_cidr", "").strip() or "0.0.0.0/0"
            secure_instance_type = request.form.get("secure_instance_type", "").strip() or "t3.micro"

            github_repo_url = request.form.get("github_repo_url", "").strip()
            github_branch = request.form.get("github_branch", "").strip() or "main"
            app_root_subdir = request.form.get("app_root_subdir", "").strip()
            domain_name = request.form.get("domain_name", "").strip()

            if not github_repo_url:
                flash("GitHub repository URL is required for Secure Web Hosting template.", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            if not domain_name:
                flash("Domain name is required for Secure Web Hosting template (it can be planned/future domain).", "danger")
                return render_template("deploy_template.html", templates=available_templates)

            tf_vars = {
                "aws_region": aws_region,
                "instance_name": instance_name,
                "key_pair_name": key_pair_name,
                "allowed_ssh_cidr": allowed_ssh_cidr,
                "instance_type": secure_instance_type,
                "github_repo_url": github_repo_url,
                "github_branch": github_branch,
                "app_root_subdir": app_root_subdir,
                "domain_name": domain_name,
            }


        else:
            flash("Unknown template selected.", "danger")
            return render_template("deploy_template.html", templates=available_templates)

        # Create Job
        user_id = session.get("user_id")
        job = Job(
            user_id=user_id,
            mode="template",
            template_name=template_id,
            status="Queued",
        )
        db.session.add(job)
        db.session.commit()

        # Start background thread
        t = threading.Thread(
            target=run_template_job_async,
            args=(job.id, template_id, tf_vars, aws_access_key, aws_secret_key, aws_region),
            daemon=True,
        )
        t.start()

        flash(f"Job #{job.id} started for template '{template_id}'. Logs will update in real-time.", "info")
        return redirect(url_for("dashboard"))

    # IMPORTANT: GET pe yeh line honi hi chahiye
    return render_template("deploy_template.html", templates=available_templates)

@app.route("/deploy/custom", methods=["GET", "POST"])
@login_required
def deploy_custom():
    """
    Custom Mode:
    - User uploads a Terraform project as ZIP
    - We create Job and run Terraform in background thread
    """

    if request.method == "POST":
        file = request.files.get("tf_zip")
        aws_access_key = request.form.get("aws_access_key", "").strip()
        aws_secret_key = request.form.get("aws_secret_key", "").strip()
        aws_region = request.form.get("aws_region", "").strip() or "ap-south-1"

        if not file or file.filename == "":
            flash("Please upload a Terraform ZIP file.", "danger")
            return render_template("custom.html")

        if not aws_access_key or not aws_secret_key:
            flash("Please provide AWS credentials.", "danger")
            return render_template("custom.html")

        filename = secure_filename(file.filename)
        if not filename.lower().endswith(".zip"):
            flash("Only .zip files are allowed.", "danger")
            return render_template("custom.html")

        zip_path = os.path.join(UPLOAD_DIR, f"job_upload_{datetime.utcnow().timestamp()}_{filename}")
        file.save(zip_path)

        user_id = session.get("user_id")
        job = Job(
            user_id=user_id,
            mode="custom",
            template_name=None,
            status="Queued",
        )
        db.session.add(job)
        db.session.commit()

        # Start background thread
        t = threading.Thread(
            target=run_custom_job_async,
            args=(job.id, zip_path, aws_access_key, aws_secret_key, aws_region),
            daemon=True,
        )
        t.start()

        flash(f"Custom job #{job.id} started. Logs will update in real-time.", "info")
        return redirect(url_for("dashboard"))

    return render_template("custom.html")



# -------------------------
# Main Entry
# -------------------------

if __name__ == "__main__":
    # Debug mode for development
    app.run(host="0.0.0.0", port=5000, debug=True)
