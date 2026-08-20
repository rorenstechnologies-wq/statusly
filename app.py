from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_from_directory
)

import json
import os
import traceback
import uuid
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from flask_cors import CORS

import firebase_admin
from firebase_admin import (
    credentials,
    db,
    auth,
    messaging
)


# ============================================================
# LOAD ENV
# ============================================================

load_dotenv()


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

CORS(app)


# ============================================================
# FIREBASE
# ============================================================

FIREBASE_SERVICE_ACCOUNT = os.environ.get(
    "FIREBASE_SERVICE_ACCOUNT",
    ""
).strip()

if not FIREBASE_SERVICE_ACCOUNT:
    raise RuntimeError(
        "FIREBASE_SERVICE_ACCOUNT environment variable is missing"
    )

try:
    firebase_service_account = json.loads(
        FIREBASE_SERVICE_ACCOUNT
    )
except json.JSONDecodeError as e:
    raise RuntimeError(
        f"FIREBASE_SERVICE_ACCOUNT contains invalid JSON: {e}"
    )


if not firebase_admin._apps:

    cred = credentials.Certificate(
        firebase_service_account
    )

    firebase_admin.initialize_app(
        cred,
        {
            "databaseURL":
                "https://hospital-57fc8-default-rtdb.firebaseio.com"
        }
    )


# ============================================================
# STATUSLY
# ============================================================

STATUSLY_BASE_URL = os.environ.get(
    "STATUSLY_BASE_URL",
    "https://statusly.in"
).strip().rstrip("/")


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# ============================================================
# LOGIN PAGE
# ============================================================

@app.route("/login-page")
def login_page():

    return render_template(
        "login.html"
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    return render_template(
        "dashboard.html"
    )


# ============================================================
# SAVE HOSPITAL
# ============================================================

@app.route(
    "/save_hospital",
    methods=["POST"]
)
def save_hospital():

    try:

        # ----------------------------------------------------
        # UID
        # ----------------------------------------------------

        uid = request.form.get(
            "uid",
            ""
        ).strip()

        if not uid:

            return jsonify({
                "success": False,
                "error": "UID missing"
            }), 400


        # ----------------------------------------------------
        # CHECK SUBSCRIPTION
        # ----------------------------------------------------

        subscription = db.reference(
            "subscriptions"
        ).child(
            uid
        ).get()

        if not subscription:

            return jsonify({
                "success": False,
                "error": "Active subscription required"
            }), 403


        if subscription.get("payment_status") != "PAID":

            return jsonify({
                "success": False,
                "error": "Subscription is not active"
            }), 403


        expiry_string = subscription.get(
            "expiry"
        )

        if not expiry_string:

            return jsonify({
                "success": False,
                "error": "Subscription expiry missing"
            }), 403


        try:

            expiry = datetime.fromisoformat(
                expiry_string
            )

            if datetime.utcnow() >= expiry:

                return jsonify({
                    "success": False,
                    "error": "Subscription expired"
                }), 403

        except Exception:

            return jsonify({
                "success": False,
                "error": "Invalid subscription expiry"
            }), 403


        # ----------------------------------------------------
        # DOCTORS
        # ----------------------------------------------------

        names = request.form.getlist(
            "doctor_name"
        )

        specs = request.form.getlist(
            "specialization"
        )

        times = request.form.getlist(
            "opd_time"
        )

        infos = request.form.getlist(
            "doctor_info"
        )


        doctors = []

        count = max(
            len(names),
            len(specs),
            len(times),
            len(infos)
        )


        for i in range(count):

            doctors.append({

                "doctor_name":
                    names[i]
                    if i < len(names)
                    else "",

                "specialization":
                    specs[i]
                    if i < len(specs)
                    else "",

                "opd_time":
                    times[i]
                    if i < len(times)
                    else "",

                "doctor_info":
                    infos[i]
                    if i < len(infos)
                    else ""

            })


        # ----------------------------------------------------
        # HOSPITAL DATA
        # ----------------------------------------------------

        hospital_data = {

            "uid":
                uid,

            "hospital_name":
                request.form.get(
                    "hospital_name",
                    ""
                ).strip(),

            "date":
                request.form.get(
                    "date",
                    ""
                ),

            "open_time":
                request.form.get(
                    "open_time",
                    ""
                ),

            "close_time":
                request.form.get(
                    "close_time",
                    ""
                ),

            "info":
                request.form.get(
                    "info",
                    ""
                ),

            "created_at":
                datetime.utcnow().isoformat(),

            "doctors":
                doctors

        }


        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        db.reference(
            "hospitals"
        ).child(
            uid
        ).set(
            hospital_data
        )


        # ----------------------------------------------------
        # IMPORTANT URLs
        # ----------------------------------------------------

        hospital_url = (
            f"{STATUSLY_BASE_URL}"
            f"/hospital/"
            f"{uid}"
        )

        booking_url = (
            f"{STATUSLY_BASE_URL}"
            f"/hospital/"
            f"{uid}"
            f"/book"
        )


        print("=" * 60)
        print("HOSPITAL SAVED")
        print("UID:", uid)
        print("HOSPITAL URL:", hospital_url)
        print("BOOKING URL:", booking_url)
        print("=" * 60)


        return jsonify({

            "success":
                True,

            "message":
                "Hospital saved successfully",

            "uid":
                uid,

            "hospital_url":
                hospital_url,

            "booking_url":
                booking_url

        })


    except Exception as e:

        print(
            "SAVE HOSPITAL ERROR:",
            str(e)
        )

        traceback.print_exc()

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# HOSPITAL PUBLIC PAGE
# ============================================================

@app.route(
    "/hospital/<uid>",
    methods=["GET"]
)
def hospital_page(uid):

    print(
        "=========================================="
    )

    print(
        "HOSPITAL PAGE REQUEST"
    )

    print(
        "UID:",
        uid
    )

    print(
        "URL:",
        request.url
    )

    print(
        "=========================================="
    )


    hospital = db.reference(
        "hospitals"
    ).child(
        uid
    ).get()


    if not hospital:

        print(
            "HOSPITAL NOT FOUND:",
            uid
        )

        return (
            "Hospital not found",
            404
        )


    return render_template(

        "hospital.html",

        hospital=hospital,

        uid=uid

    )


# ============================================================
# BOOKING PAGE
# ============================================================

@app.route(
    "/hospital/<uid>/book",
    methods=["GET"]
)
def book_page(uid):

    print(
        "BOOK PAGE REQUEST:",
        uid
    )


    hospital = db.reference(
        "hospitals"
    ).child(
        uid
    ).get()


    if not hospital:

        return (
            "Hospital not found",
            404
        )


    return render_template(

        "appointment.html",

        hospital=hospital,

        uid=uid

    )


# ============================================================
# TEST HOSPITAL ROUTE
# ============================================================

@app.route(
    "/test-hospital/<uid>"
)
def test_hospital(uid):

    hospital = db.reference(
        "hospitals"
    ).child(
        uid
    ).get()


    return jsonify({

        "uid":
            uid,

        "hospital":
            hospital

    })


# ============================================================
# HEALTH
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "success":
            True,

        "status":
            "online",

        "service":
            "Statusly",

        "time":
            datetime.utcnow().isoformat()

    })


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(

        debug=True,

        host="0.0.0.0",

        port=5000

    )
