import os
import json
from datetime import datetime, timezone

from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, db, auth


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# FIREBASE INITIALIZATION
# ============================================================

def initialize_firebase():

    if firebase_admin._apps:
        return

    # --------------------------------------------------------
    # Option 1:
    # FIREBASE_SERVICE_ACCOUNT environment variable
    # --------------------------------------------------------

    service_account_json = os.environ.get(
        "FIREBASE_SERVICE_ACCOUNT"
    )

    if service_account_json:

        service_account = credentials.Certificate(
            json.loads(service_account_json)
        )

    # --------------------------------------------------------
    # Option 2:
    # serviceAccountKey.json
    # --------------------------------------------------------

    elif os.path.exists("serviceAccountKey.json"):

        service_account = credentials.Certificate(
            "serviceAccountKey.json"
        )

    else:

        raise RuntimeError(
            "Firebase service account not configured. "
            "Set FIREBASE_SERVICE_ACCOUNT or add "
            "serviceAccountKey.json."
        )

    database_url = os.environ.get(
        "FIREBASE_DATABASE_URL"
    )

    if not database_url:

        raise RuntimeError(
            "FIREBASE_DATABASE_URL is missing."
        )

    firebase_admin.initialize_app(
        service_account,
        {
            "databaseURL": database_url
        }
    )


try:

    initialize_firebase()

    FIREBASE_READY = True

except Exception as e:

    print("Firebase initialization failed:")
    print(e)

    FIREBASE_READY = False


# ============================================================
# FIREBASE AUTH
# ============================================================

def verify_user():

    authorization = request.headers.get(
        "Authorization",
        ""
    )

    if not authorization:

        return None, "Authorization header missing"

    if not authorization.startswith(
        "Bearer "
    ):

        return None, "Invalid authorization header"

    token = authorization[7:].strip()

    if not token:

        return None, "Firebase token missing"

    try:

        decoded_token = auth.verify_id_token(
            token
        )

        return decoded_token, None

    except Exception as e:

        print("Firebase authentication error:")
        print(e)

        return None, "Invalid or expired Firebase token"


# ============================================================
# HELPERS
# ============================================================

def as_dict(value):

    if isinstance(value, dict):
        return value

    return {}


def as_list(value):

    if isinstance(value, list):
        return value

    if isinstance(value, dict):

        result = []

        for key, item in value.items():

            if isinstance(item, dict):

                item = dict(item)

                item.setdefault(
                    "id",
                    key
                )

                result.append(item)

        return result

    return []


def get_today():

    return datetime.now().strftime(
        "%Y-%m-%d"
    )


# ============================================================
# HOSPITAL
# ============================================================

def get_hospital(uid):

    try:

        hospital = db.reference(
            f"hospitals/{uid}"
        ).get()

        if not hospital:

            return {}

        return as_dict(
            hospital
        )

    except Exception as e:

        print("Hospital error:", e)

        return {}


# ============================================================
# DOCTORS
# ============================================================

def get_doctors(hospital):

    doctors = hospital.get(
        "doctors",
        {}
    )

    return as_list(
        doctors
    )


# ============================================================
# APPOINTMENTS
# ============================================================

def get_all_appointments(uid):

    try:

        data = db.reference(
            "appointments"
        ).get()

        if not data:

            return []

        appointments = []

        if isinstance(
            data,
            dict
        ):

            items = data.items()

        elif isinstance(
            data,
            list
        ):

            items = enumerate(data)

        else:

            return []

        for appointment_id, item in items:

            if not isinstance(
                item,
                dict
            ):
                continue

            appointment = dict(
                item
            )

            appointment.setdefault(
                "id",
                appointment_id
            )

            hospital_id = (
                appointment.get(
                    "hospital_id"
                )
                or
                appointment.get(
                    "hospitalId"
                )
            )

            if str(hospital_id) != str(uid):

                continue

            appointments.append(
                appointment
            )

        return appointments

    except Exception as e:

        print("Appointments error:", e)

        return []


# ============================================================
# TODAY APPOINTMENTS
# ============================================================

def get_today_appointments(uid):

    appointments = get_all_appointments(
        uid
    )

    today = get_today()

    result = []

    for appointment in appointments:

        appointment_date = (
            appointment.get(
                "appointment_date"
            )
            or
            appointment.get(
                "appointmentDate"
            )
            or
            appointment.get(
                "date"
            )
        )

        if str(
            appointment_date
        )[:10] == today:

            result.append({

                "patient_no":
                    appointment.get(
                        "patient_no"
                    )
                    or
                    appointment.get(
                        "patientNo"
                    )
                    or
                    appointment.get(
                        "token_no"
                    )
                    or
                    "-",

                "patient_name":
                    appointment.get(
                        "patient_name"
                    )
                    or
                    appointment.get(
                        "patientName"
                    )
                    or
                    appointment.get(
                        "name"
                    )
                    or
                    "-",

                "doctor_name":
                    appointment.get(
                        "doctor_name"
                    )
                    or
                    appointment.get(
                        "doctorName"
                    )
                    or
                    appointment.get(
                        "doctor"
                    )
                    or
                    "-",

                "appointment_time":
                    appointment.get(
                        "appointment_time"
                    )
                    or
                    appointment.get(
                        "appointmentTime"
                    )
                    or
                    appointment.get(
                        "time"
                    )
                    or
                    "-",

                "mobile":
                    appointment.get(
                        "mobile"
                    )
                    or
                    appointment.get(
                        "phone"
                    )
                    or
                    "-"

            })

    result.sort(
        key=lambda x:
            str(
                x.get(
                    "appointment_time",
                    ""
                )
            )
    )

    return result


# ============================================================
# FOLLOWUPS
# ============================================================

def get_followups(uid):

    try:

        data = db.reference(
            "followups"
        ).get()

        if not data:

            return []

        result = []

        if isinstance(
            data,
            dict
        ):

            items = data.items()

        else:

            items = enumerate(data)

        for followup_id, item in items:

            if not isinstance(
                item,
                dict
            ):
                continue

            followup = dict(
                item
            )

            hospital_id = (
                followup.get(
                    "hospital_id"
                )
                or
                followup.get(
                    "hospitalId"
                )
            )

            if str(hospital_id) != str(uid):

                continue

            followup.setdefault(
                "id",
                followup_id
            )

            result.append(
                followup
            )

        return result

    except Exception as e:

        print("Followups error:", e)

        return []


# ============================================================
# SUBSCRIPTION
# ============================================================

def get_subscription(uid):

    try:

        data = db.reference(
            f"subscriptions/{uid}"
        ).get()

        if not data:

            return {
                "plan": "No Plan",
                "expiry": None,
                "active": False
            }

        data = as_dict(
            data
        )

        plan = data.get(
            "plan",
            "No Plan"
        )

        expiry = (
            data.get(
                "expiry"
            )
            or
            data.get(
                "expiry_date"
            )
            or
            data.get(
                "expiryDate"
            )
        )

        active = False

        if expiry:

            try:

                expiry_string = str(
                    expiry
                )

                if len(
                    expiry_string
                ) >= 10:

                    expiry_date = datetime.strptime(
                        expiry_string[:10],
                        "%Y-%m-%d"
                    ).date()

                    active = (
                        expiry_date
                        >= datetime.now().date()
                    )

            except Exception:

                active = False

        return {

            "plan":
                plan,

            "expiry":
                expiry,

            "active":
                active

        }

    except Exception as e:

        print("Subscription error:", e)

        return {

            "plan":
                "No Plan",

            "expiry":
                None,

            "active":
                False

        }


# ============================================================
# DASHBOARD API
# ============================================================

@app.route(
    "/api/dashboard",
    methods=["GET"]
)
def dashboard_api():

    if not FIREBASE_READY:

        return jsonify({

            "success":
                False,

            "error":
                "Firebase is not configured"

        }), 500

    # --------------------------------------------------------
    # Verify Firebase user
    # --------------------------------------------------------

    user, error = verify_user()

    if error:

        return jsonify({

            "success":
                False,

            "error":
                error

        }), 401

    uid = user.get(
        "uid"
    )

    if not uid:

        return jsonify({

            "success":
                False,

            "error":
                "UID not found"

        }), 401

    try:

        # ----------------------------------------------------
        # Hospital
        # ----------------------------------------------------

        hospital = get_hospital(
            uid
        )

        # ----------------------------------------------------
        # Doctors
        # ----------------------------------------------------

        doctors = get_doctors(
            hospital
        )

        # ----------------------------------------------------
        # Appointments
        # ----------------------------------------------------

        all_appointments = (
            get_all_appointments(
                uid
            )
        )

        today_appointments = (
            get_today_appointments(
                uid
            )
        )

        # ----------------------------------------------------
        # Followups
        # ----------------------------------------------------

        followups = get_followups(
            uid
        )

        # ----------------------------------------------------
        # Subscription
        # ----------------------------------------------------

        subscription = get_subscription(
            uid
        )

        # ----------------------------------------------------
        # URLs
        # ----------------------------------------------------

        base_url = request.host_url.rstrip(
            "/"
        )

        hospital_url = (
            f"{base_url}/hospital/{uid}"
        )

        booking_url = (
            f"{base_url}/hospital/{uid}/book"
        )

        # ----------------------------------------------------
        # Response
        # ----------------------------------------------------

        return jsonify({

            "success":
                True,

            "uid":
                uid,

            "hospital":
                hospital,

            "stats": {

                "doctors":
                    len(doctors),

                "today":
                    len(today_appointments),

                "appointments":
                    len(all_appointments),

                "followups":
                    len(followups)

            },

            "subscription": {

                "plan":
                    subscription.get(
                        "plan"
                    ),

                "expiry":
                    subscription.get(
                        "expiry"
                    )

            },

            "subscription_active":
                subscription.get(
                    "active",
                    False
                ),

            "today_appointments":
                today_appointments,

            "doctors":
                doctors,

            "hospital_url":
                hospital_url,

            "booking_url":
                booking_url

        })

    except Exception as e:

        print(
            "Dashboard API error:",
            e
        )

        return jsonify({

            "success":
                False,

            "error":
                "Dashboard loading failed"

        }), 500


# ============================================================
# DASHBOARD PAGE
# ============================================================

@app.route(
    "/dashboard"
)
def dashboard():

    return render_template(
        "dashboard.html",

        firebase_api_key=os.environ.get(
            "FIREBASE_API_KEY",
            ""
        ),

        firebase_auth_domain=os.environ.get(
            "FIREBASE_AUTH_DOMAIN",
            ""
        ),

        firebase_database_url=os.environ.get(
            "FIREBASE_DATABASE_URL",
            ""
        ),

        firebase_project_id=os.environ.get(
            "FIREBASE_PROJECT_ID",
            ""
        ),

        firebase_storage_bucket=os.environ.get(
            "FIREBASE_STORAGE_BUCKET",
            ""
        ),

        firebase_messaging_sender_id=os.environ.get(
            "FIREBASE_MESSAGING_SENDER_ID",
            ""
        )
    )


# ============================================================
# HOSPITAL PAGE
# ============================================================

@app.route(
    "/hospital/<uid>"
)
def hospital_page(uid):

    hospital = get_hospital(
        uid
    )

    if not hospital:

        return "Hospital not found", 404

    return render_template(
        "hospital.html",
        hospital=hospital,
        uid=uid
    )


# ============================================================
# BOOKING PAGE
# ============================================================

@app.route(
    "/hospital/<uid>/book"
)
def booking_page(uid):

    hospital = get_hospital(
        uid
    )

    if not hospital:

        return "Hospital not found", 404

    return render_template(
        "booking.html",
        hospital=hospital,
        uid=uid
    )


# ============================================================
# APPOINTMENTS PAGE
# ============================================================

@app.route(
    "/appointments/<uid>"
)
def appointments_page(uid):

    return render_template(
        "appointments.html",
        uid=uid
    )


# ============================================================
# FOLLOWUPS PAGE
# ============================================================

@app.route(
    "/followups/<uid>"
)
def followups_page(uid):

    return render_template(
        "followups.html",
        uid=uid
    )


# ============================================================
# LOGIN PAGE
# ============================================================

@app.route(
    "/login-page"
)
def login_page():

    return render_template(
        "login.html"
    )


# ============================================================
# HEALTH
# ============================================================

@app.route(
    "/health"
)
def health():

    return jsonify({

        "success":
            True,

        "firebase":
            FIREBASE_READY

    })


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
