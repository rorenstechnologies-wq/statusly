from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS

import firebase_admin
from firebase_admin import credentials, db, auth, messaging

from datetime import datetime, timedelta
from collections import Counter

import json
import os
import requests
import traceback
import uuid

from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

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
# AISENSY
# ============================================================

AISENSY_API_KEY = os.environ.get(
    "AISENSY_API_KEY",
    ""
).strip()

AISENSY_API_URL = (
    "https://backend.aisensy.com/campaign/t1/api/v2"
)

AISENSY_APPOINTMENT_CAMPAIGN = (
    "MediQueue Appointment Confirmation"
)

AISENSY_FOLLOWUP_CAMPAIGN = (
    "mediqueue_followup_reminder"
)


# ============================================================
# CASHFREE
# ============================================================

CASHFREE_CLIENT_ID = os.environ.get(
    "CASHFREE_CLIENT_ID",
    ""
).strip()

CASHFREE_CLIENT_SECRET = os.environ.get(
    "CASHFREE_CLIENT_SECRET",
    ""
).strip()

CASHFREE_BASE_URL = os.environ.get(
    "CASHFREE_BASE_URL",
    "https://api.cashfree.com/pg"
).strip().rstrip("/")

CASHFREE_API_VERSION = os.environ.get(
    "CASHFREE_API_VERSION",
    "2025-01-01"
).strip()

STATUSLY_BASE_URL = os.environ.get(
    "STATUSLY_BASE_URL",
    "https://statusly.in"
).strip().rstrip("/")


# ============================================================
# SUBSCRIPTION PLANS
# ============================================================

PLANS = {
    "basic": {
        "amount": 1,
        "duration_days": 30
    },

    "standard": {
        "amount": 1000,
        "duration_days": 180
    },

    "premium": {
        "amount": 2000,
        "duration_days": 365
    }
}


# ============================================================
# COMMON HELPERS
# ============================================================

def utc_now():
    return datetime.utcnow()


def format_whatsapp_number(mobile):
    if not mobile:
        return ""

    mobile = "".join(
        filter(
            str.isdigit,
            str(mobile).strip()
        )
    )

    if len(mobile) == 10:
        mobile = "91" + mobile

    return mobile


def cashfree_headers():
    return {
        "x-client-id": CASHFREE_CLIENT_ID,
        "x-client-secret": CASHFREE_CLIENT_SECRET,
        "x-api-version": CASHFREE_API_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


# ============================================================
# FIREBASE AUTH
# ============================================================

def get_authenticated_user():

    authorization = request.headers.get(
        "Authorization",
        ""
    )

    if not authorization:
        print("AUTH ERROR: Authorization header missing")
        return None

    if not authorization.startswith("Bearer "):
        print("AUTH ERROR: Invalid Authorization format")
        return None

    token = authorization[7:].strip()

    if not token:
        print("AUTH ERROR: Firebase token missing")
        return None

    try:
        decoded = auth.verify_id_token(token)

        print(
            "FIREBASE USER:",
            decoded.get("uid"),
            decoded.get("email")
        )

        return decoded

    except Exception as e:
        print("FIREBASE AUTH ERROR:", str(e))
        traceback.print_exc()
        return None


# ============================================================
# SUBSCRIPTION HELPERS
# ============================================================

def get_subscription(uid):

    if not uid:
        return None

    return (
        db.reference("subscriptions")
        .child(uid)
        .get()
    )


def subscription_is_active(uid):

    subscription = get_subscription(uid)

    if not subscription:
        return False

    if subscription.get("payment_status") != "PAID":
        return False

    expiry_string = subscription.get("expiry")

    if not expiry_string:
        return False

    try:
        expiry = datetime.fromisoformat(
            expiry_string
        )

        return utc_now() < expiry

    except Exception as e:
        print(
            "SUBSCRIPTION EXPIRY ERROR:",
            str(e)
        )
        return False


# ============================================================
# FIREBASE SERVICE WORKER
# ============================================================

@app.route("/firebase-messaging-sw.js")
def firebase_sw():

    return send_from_directory(
        "static",
        "firebase-messaging-sw.js"
    )


# ============================================================
# BASIC PAGES
# ============================================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login-page")
def login_page():
    return render_template("login.html")


@app.route("/payment")
def payment():
    return render_template("payment.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/temp-dash")
def temp_dash():

    order_id = request.args.get(
        "order_id",
        ""
    )

    return render_template(
        "temp-dash.html",
        order_id=order_id
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["POST"])
def login():

    try:

        decoded = get_authenticated_user()

        if not decoded:
            return jsonify({
                "error": "Authentication required"
            }), 401

        uid = decoded.get("uid")

        hospital = (
            db.reference(
                f"hospitals/{uid}"
            ).get()
            or {}
        )

        return jsonify({

            "uid": uid,

            "hospitalId":
                hospital.get(
                    "hospitalId",
                    ""
                ),

            "hospitalName":
                hospital.get(
                    "hospital_name",
                    ""
                )

        })

    except Exception as e:

        print("LOGIN ERROR:", str(e))
        traceback.print_exc()

        return jsonify({
            "error": str(e)
        }), 401


# ============================================================
# CREATE CASHFREE PAYMENT ORDER
# ============================================================

@app.route(
    "/create-payment-order",
    methods=["POST"]
)
def create_payment_order():

    try:

        decoded = get_authenticated_user()

        if not decoded:
            return jsonify({
                "success": False,
                "error": "Authentication required"
            }), 401

        uid = decoded.get("uid")

        if not uid:
            return jsonify({
                "success": False,
                "error": "UID missing"
            }), 400

        data = request.get_json(
            silent=True
        ) or {}

        plan = str(
            data.get(
                "plan",
                "basic"
            )
        ).lower()

        if plan not in PLANS:
            return jsonify({
                "success": False,
                "error": "Invalid plan"
            }), 400

        plan_data = PLANS[plan]

        amount = plan_data["amount"]
        duration_days = plan_data["duration_days"]

        if not CASHFREE_CLIENT_ID:
            return jsonify({
                "success": False,
                "error": "CASHFREE_CLIENT_ID is missing"
            }), 500

        if not CASHFREE_CLIENT_SECRET:
            return jsonify({
                "success": False,
                "error": "CASHFREE_CLIENT_SECRET is missing"
            }), 500

        customer_name = data.get(
            "customer_name",
            "Statusly Customer"
        )

        customer_email = data.get(
            "customer_email",
            decoded.get("email", "")
        )

        customer_phone = data.get(
            "customer_phone",
            ""
        )

        customer_phone = "".join(
            filter(
                str.isdigit,
                str(customer_phone)
            )
        )

        if not customer_phone:
            customer_phone = "9999999999"

        if len(customer_phone) == 12:
            customer_phone = customer_phone[-10:]

        if len(customer_phone) != 10:
            return jsonify({
                "success": False,
                "error": "Valid 10 digit customer phone is required"
            }), 400

        order_id = (
            "STATUSLY_"
            + uuid.uuid4().hex
        )

        return_url = (
            f"{STATUSLY_BASE_URL}"
            f"/temp-dash"
            f"?order_id={order_id}"
        )

        payload = {

            "order_id":
                order_id,

            "order_amount":
                float(amount),

            "order_currency":
                "INR",

            "customer_details": {

                "customer_id":
                    uid,

                "customer_name":
                    customer_name,

                "customer_email":
                    customer_email
                    or
                    f"{uid}@statusly.in",

                "customer_phone":
                    customer_phone
            },

            "order_meta": {

                "return_url":
                    return_url
            },

            "order_note":
                f"Statusly {plan} subscription"
        }

        print("Creating Cashfree order:", order_id)

        response = requests.post(

            f"{CASHFREE_BASE_URL}/orders",

            headers=cashfree_headers(),

            json=payload,

            timeout=30
        )

        print(
            "CASHFREE CREATE:",
            response.status_code,
            response.text
        )

        if not response.ok:

            return jsonify({

                "success": False,

                "error":
                    "Cashfree order creation failed",

                "cashfree_status":
                    response.status_code,

                "cashfree_response":
                    response.text

            }), response.status_code

        result = response.json()

        payment_session_id = result.get(
            "payment_session_id"
        )

        if not payment_session_id:

            return jsonify({

                "success": False,

                "error":
                    "payment_session_id missing",

                "cashfree_response":
                    result

            }), 500

        db.reference(
            "payment_orders"
        ).child(
            order_id
        ).set({

            "order_id":
                order_id,

            "uid":
                uid,

            "plan":
                plan,

            "amount":
                amount,

            "duration_days":
                duration_days,

            "payment_status":
                "CREATED",

            "payment_session_id":
                payment_session_id,

            "subscription_activated":
                False,

            "customer_name":
                customer_name,

            "customer_email":
                customer_email,

            "customer_phone":
                customer_phone,

            "created_at":
                utc_now().isoformat()

        })

        return jsonify({

            "success":
                True,

            "order_id":
                order_id,

            "payment_session_id":
                payment_session_id,

            "plan":
                plan,

            "amount":
                amount

        })

    except Exception as e:

        print(
            "CREATE PAYMENT ORDER ERROR:",
            str(e)
        )

        traceback.print_exc()

        return jsonify({

            "success": False,

            "error": str(e)

        }), 500


# ============================================================
# ACTIVATE SUBSCRIPTION
# ============================================================

def activate_subscription(order_id):

    try:

        payment_ref = (
            db.reference("payment_orders")
            .child(order_id)
        )

        payment_order = payment_ref.get()

        if not payment_order:

            return {
                "success": False,
                "error": "Local payment order not found"
            }

        if payment_order.get(
            "subscription_activated"
        ):

            return {
                "success": True,
                "already_activated": True
            }

        uid = payment_order.get("uid")
        plan = payment_order.get("plan")
        amount = payment_order.get("amount")
        duration_days = payment_order.get(
            "duration_days"
        )

        if not uid or not plan:
            return {
                "success": False,
                "error": "Payment order data incomplete"
            }

        expiry = (
            utc_now()
            + timedelta(
                days=int(duration_days)
            )
        )

        payment_id = ""

        try:

            response = requests.get(

                f"{CASHFREE_BASE_URL}/orders/"
                f"{order_id}/payments",

                headers=cashfree_headers(),

                timeout=30
            )

            if response.ok:

                payments = response.json()

                if isinstance(payments, list):

                    for payment in payments:

                        if payment.get(
                            "payment_status"
                        ) == "SUCCESS":

                            payment_id = payment.get(
                                "cf_payment_id",
                                ""
                            )

                            break

        except Exception as e:

            print(
                "PAYMENT ID ERROR:",
                str(e)
            )

        subscription_data = {

            "uid":
                uid,

            "plan":
                plan,

            "amount":
                amount,

            "duration_days":
                duration_days,

            "payment_status":
                "PAID",

            "expiry":
                expiry.isoformat(),

            "cashfree_order_id":
                order_id,

            "cashfree_payment_id":
                payment_id,

            "updated_at":
                utc_now().isoformat()
        }

        db.reference(
            "subscriptions"
        ).child(
            uid
        ).set(
            subscription_data
        )

        payment_ref.update({

            "subscription_activated":
                True,

            "payment_status":
                "PAID",

            "cashfree_payment_id":
                payment_id,

            "subscription_expiry":
                expiry.isoformat(),

            "activated_at":
                utc_now().isoformat()
        })

        print(
            "SUBSCRIPTION ACTIVATED:",
            uid,
            plan
        )

        return {

            "success":
                True,

            "subscription":
                subscription_data
        }

    except Exception as e:

        print(
            "ACTIVATE SUBSCRIPTION ERROR:",
            str(e)
        )

        traceback.print_exc()

        return {

            "success":
                False,

            "error":
                str(e)
        }


# ============================================================
# CASHFREE ORDER STATUS
# ============================================================

@app.route(
    "/cashfree/order-status/<order_id>",
    methods=["GET"]
)
def cashfree_order_status(order_id):

    try:

        local_order = (
            db.reference("payment_orders")
            .child(order_id)
            .get()
        )

        if not local_order:

            return jsonify({

                "success":
                    False,

                "error":
                    "Local payment order not found"

            }), 404

        response = requests.get(

            f"{CASHFREE_BASE_URL}/orders/"
            f"{order_id}",

            headers=cashfree_headers(),

            timeout=30
        )

        if not response.ok:

            return jsonify({

                "success":
                    False,

                "error":
                    "Unable to check Cashfree order",

                "cashfree_status":
                    response.status_code,

                "cashfree_response":
                    response.text

            }), response.status_code

        cashfree_order = response.json()

        status = cashfree_order.get(
            "order_status"
        )

        print(
            "CASHFREE ORDER STATUS:",
            order_id,
            status
        )

        if status == "PAID":

            activation = activate_subscription(
                order_id
            )

            return jsonify({

                "success":
                    True,

                "paid":
                    True,

                "order_id":
                    order_id,

                "order_status":
                    "PAID",

                "activation":
                    activation

            })

        db.reference(
            "payment_orders"
        ).child(
            order_id
        ).update({

            "payment_status":
                status or "UNKNOWN",

            "last_checked_at":
                utc_now().isoformat()
        })

        return jsonify({

            "success":
                True,

            "paid":
                False,

            "order_id":
                order_id,

            "order_status":
                status

        })

    except Exception as e:

        print(
            "ORDER STATUS ERROR:",
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
# CASHFREE WEBHOOK
# ============================================================

@app.route(
    "/cashfree/webhook",
    methods=["POST"]
)
def cashfree_webhook():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        print(
            "CASHFREE WEBHOOK:",
            data
        )

        order_id = (
            data
            .get("data", {})
            .get("order", {})
            .get("order_id")
        )

        if not order_id:
            return "EVENT_RECEIVED", 200

        response = requests.get(

            f"{CASHFREE_BASE_URL}/orders/"
            f"{order_id}",

            headers=cashfree_headers(),

            timeout=30
        )

        if response.ok:

            order_data = response.json()

            if order_data.get(
                "order_status"
            ) == "PAID":

                activate_subscription(
                    order_id
                )

        return "EVENT_RECEIVED", 200

    except Exception as e:

        print(
            "CASHFREE WEBHOOK ERROR:",
            str(e)
        )

        traceback.print_exc()

        return "EVENT_RECEIVED", 200


# ============================================================
# CHECK SUBSCRIPTION
# ============================================================

@app.route(
    "/check-subscription",
    methods=["POST"]
)
def check_subscription():

    try:

        decoded = get_authenticated_user()

        if not decoded:

            return jsonify({

                "success":
                    False,

                "error":
                    "Authentication required"

            }), 401

        uid = decoded.get("uid")

        subscription = get_subscription(
            uid
        )

        active = subscription_is_active(
            uid
        )

        return jsonify({

            "success":
                True,

            "uid":
                uid,

            "active":
                active,

            "subscription":
                subscription or {}

        })

    except Exception as e:

        print(
            "CHECK SUBSCRIPTION ERROR:",
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
# SAVE HOSPITAL
# ============================================================

@app.route(
    "/save_hospital",
    methods=["POST"]
)
def save_hospital():

    try:

        # ----------------------------------------------------
        # AUTHENTICATE USER
        # ----------------------------------------------------

        decoded = get_authenticated_user()

        if not decoded:

            return jsonify({

                "success":
                    False,

                "error":
                    "Authentication required"

            }), 401

        uid = decoded.get("uid")

        if not uid:

            return jsonify({

                "success":
                    False,

                "error":
                    "UID missing"

            }), 400

        # ----------------------------------------------------
        # CHECK SUBSCRIPTION
        # ----------------------------------------------------

        if not subscription_is_active(uid):

            return jsonify({

                "success":
                    False,

                "error":
                    "Active subscription required"

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

        for i in range(
            min(
                len(names),
                len(specs),
                len(times),
                len(infos)
            )
        ):

            doctors.append({

                "doctor_name":
                    names[i],

                "specialization":
                    specs[i],

                "opd_time":
                    times[i],

                "doctor_info":
                    infos[i]
            })

        # ----------------------------------------------------
        # HOSPITAL DATA
        # ----------------------------------------------------

        hospital_data = {

            "uid":
                uid,

            "hospital_name":
                request.form.get(
                    "hospital_name"
                ),

            "date":
                request.form.get(
                    "date"
                ),

            "open_time":
                request.form.get(
                    "open_time"
                ),

            "close_time":
                request.form.get(
                    "close_time"
                ),

            "info":
                request.form.get(
                    "info"
                ),

            "created_at":
                utc_now().isoformat(),

            "doctors":
                doctors
        }

        db.reference(
            "hospitals"
        ).child(
            uid
        ).set(
            hospital_data
        )

        return jsonify({

            "success":
                True,

            "message":
                "Hospital saved",

            "uid":
                uid

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
# HOSPITAL PAGE
# ============================================================

@app.route(
    "/hospital/<uid>"
)
def hospital_page(uid):

    data = (
        db.reference(
            f"hospitals/{uid}"
        ).get()
    )

    if not data:

        return (
            "Hospital not found",
            404
        )

    return render_template(

        "hospital.html",

        hospital=data,

        uid=uid
    )


# ============================================================
# BOOK PAGE
# ============================================================

@app.route(
    "/hospital/<uid>/book"
)
def book_page(uid):

    hospital = (
        db.reference(
            f"hospitals/{uid}"
        ).get()
    )

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
# BOOK APPOINTMENT
# ============================================================

@app.route(
    "/book_appointment",
    methods=["POST"]
)
def book_appointment():

    try:

        hospital_id = request.form.get(
            "hospital_id"
        )

        if not hospital_id:

            return jsonify({

                "success":
                    False,

                "error":
                    "Hospital ID missing"

            }), 400

        # ----------------------------------------------------
        # PATIENT NUMBER
        # ----------------------------------------------------

        counter_ref = db.reference(
            "counters/patient_no"
        )

        patient_no = (
            counter_ref.get() or 0
        ) + 1

        counter_ref.set(
            patient_no
        )

        # ----------------------------------------------------
        # APPOINTMENT
        # ----------------------------------------------------

        appointment = {

            "hospital_id":
                hospital_id,

            "patient_no":
                patient_no,

            "doctor_name":
                request.form.get(
                    "doctor_name"
                ),

            "patient_name":
                request.form.get(
                    "patient_name"
                ),

            "gender":
                request.form.get(
                    "gender"
                ),

            "age":
                request.form.get(
                    "age"
                ),

            "mobile":
                request.form.get(
                    "mobile"
                ),

            "address":
                request.form.get(
                    "address"
                ),

            "appointment_date":
                request.form.get(
                    "appointment_date"
                ),

            "appointment_time":
                request.form.get(
                    "appointment_time"
                ),

            "created_at":
                utc_now().isoformat()
        }

        ref = (
            db.reference("appointments")
            .push(appointment)
        )

        patient_id = ref.key

        # ----------------------------------------------------
        # FCM TOKEN
        # ----------------------------------------------------

        fcm_token = request.form.get(
            "fcm_token"
        )

        if fcm_token:

            db.reference(
                "notification_tokens"
            ).child(
                patient_id
            ).set({

                "token":
                    fcm_token
            })

        # ----------------------------------------------------
        # WHATSAPP
        # ----------------------------------------------------

        whatsapp_result = (
            send_aisensy_appointment_confirmation(
                patient_id
            )
        )

        print(
            "Appointment WhatsApp:",
            whatsapp_result
        )

        # ----------------------------------------------------
        # HOSPITAL DATA
        # ----------------------------------------------------

        hospital = (
            db.reference(
                f"hospitals/{hospital_id}"
            ).get()
            or {}
        )

        hospital_name = hospital.get(
            "hospital_name",
            "Hospital"
        )

        doctor_name = appointment.get(
            "doctor_name",
            "Doctor"
        )

        specialization = ""

        for doctor in hospital.get(
            "doctors",
            []
        ):

            if doctor.get(
                "doctor_name"
            ) == doctor_name:

                specialization = doctor.get(
                    "specialization",
                    ""
                )

                break

        # ----------------------------------------------------
        # SUCCESS PAGE
        # ----------------------------------------------------

        return render_template(

            "success.html",

            patient_id=patient_id,

            hospital_name=hospital_name,

            doctor_name=doctor_name,

            specialization=specialization,

            appointment_date=
                appointment.get(
                    "appointment_date",
                    ""
                ),

            appointment_time=
                appointment.get(
                    "appointment_time",
                    ""
                )
        )

    except Exception as e:

        print(
            "BOOK APPOINTMENT ERROR:",
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
# GET HOSPITAL APPOINTMENTS
# ============================================================

def get_hospital_appointments(hospital_id):

    if not hospital_id:
        return []

    data = (
        db.reference(
            "appointments"
        ).get()
        or {}
    )

    appointments = []

    for appointment_id, appointment in data.items():

        if not isinstance(
            appointment,
            dict
        ):
            continue

        if appointment.get(
            "hospital_id"
        ) != hospital_id:
            continue

        appointment = dict(
            appointment
        )

        appointment["id"] = appointment_id

        appointments.append(
            appointment
        )

    return appointments


# ============================================================
# ANALYTICS OVERVIEW
# ============================================================

@app.route(
    "/api/analytics/overview/<hospital_id>"
)
def analytics_overview(hospital_id):

    try:

        appointments = (
            get_hospital_appointments(
                hospital_id
            )
        )

        today = datetime.now().strftime(
            "%Y-%m-%d"
        )

        gender_counts = Counter()

        for appointment in appointments:

            gender = str(
                appointment.get(
                    "gender",
                    ""
                )
            ).strip().lower()

            gender_counts[gender] += 1

        return jsonify({

            "success":
                True,

            "total_patients":
                len(appointments),

            "today_appointments":
                sum(
                    1
                    for a in appointments
                    if a.get(
                        "appointment_date"
                    ) == today
                ),

            "male":
                gender_counts.get(
                    "male",
                    0
                ),

            "female":
                gender_counts.get(
                    "female",
                    0
                ),

            "other":
                sum(
                    count
                    for gender, count
                    in gender_counts.items()
                    if gender not in [
                        "male",
                        "female"
                    ]
                )
        })

    except Exception as e:

        traceback.print_exc()

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# GENDER ANALYTICS
# ============================================================

@app.route(
    "/api/analytics/gender/<hospital_id>"
)
def analytics_gender(hospital_id):

    try:

        appointments = (
            get_hospital_appointments(
                hospital_id
            )
        )

        gender = Counter()

        for appointment in appointments:

            value = str(
                appointment.get(
                    "gender",
                    "Unknown"
                )
            ).strip().title()

            if not value:
                value = "Unknown"

            gender[value] += 1

        return jsonify({

            "success":
                True,

            "data":
                dict(gender)
        })

    except Exception as e:

        traceback.print_exc()

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# AGE ANALYTICS
# ============================================================

@app.route(
    "/api/analytics/age/<hospital_id>"
)
def analytics_age(hospital_id):

    try:

        appointments = (
            get_hospital_appointments(
                hospital_id
            )
        )

        age_groups = Counter()

        for appointment in appointments:

            try:

                age = int(
                    appointment.get(
                        "age",
                        0
                    )
                )

            except Exception:

                age = 0

            if age <= 0:
                group = "Unknown"

            elif age <= 18:
                group = "0-18"

            elif age <= 30:
                group = "19-30"

            elif age <= 45:
                group = "31-45"

            elif age <= 60:
                group = "46-60"

            else:
                group = "60+"

            age_groups[group] += 1

        return jsonify({

            "success":
                True,

            "data":
                dict(age_groups)
        })

    except Exception as e:

        traceback.print_exc()

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# DOCTOR ANALYTICS
# ============================================================

@app.route(
    "/api/analytics/doctors/<hospital_id>"
)
def analytics_doctors(hospital_id):

    try:

        appointments = (
            get_hospital_appointments(
                hospital_id
            )
        )

        doctors = Counter()

        for appointment in appointments:

            doctor = str(
                appointment.get(
                    "doctor_name",
                    "Unknown"
                )
            ).strip()

            if not doctor:
                doctor = "Unknown"

            doctors[doctor] += 1

        return jsonify({

            "success":
                True,

            "data":
                dict(
                    doctors.most_common()
                )
        })

    except Exception as e:

        traceback.print_exc()

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# DAILY ANALYTICS
# ============================================================

@app.route(
    "/api/analytics/daily/<hospital_id>"
)
def analytics_daily(hospital_id):

    try:

        appointments = (
            get_hospital_appointments(
                hospital_id
            )
        )

        daily = Counter()

        for appointment in appointments:

            date = appointment.get(
                "appointment_date"
            )

            if date:
                daily[str(date)] += 1

        return jsonify({

            "success":
                True,

            "data":
                dict(
                    sorted(
                        daily.items()
                    )
                )
        })

    except Exception as e:

        traceback.print_exc()

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# TIME ANALYTICS
# ============================================================

@app.route(
    "/api/analytics/time/<hospital_id>"
)
def analytics_time(hospital_id):

    try:

        appointments = (
            get_hospital_appointments(
                hospital_id
            )
        )

        times = Counter()

        for appointment in appointments:

            time = str(
                appointment.get(
                    "appointment_time",
                    "Unknown"
                )
            ).strip()

            if not time:
                time = "Unknown"

            times[time] += 1

        return jsonify({

            "success":
                True,

            "data":
                dict(times)
        })

    except Exception as e:

        traceback.print_exc()

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# LOCATION ANALYTICS
# ============================================================

@app.route(
    "/api/analytics/location/<hospital_id>"
)
def analytics_location(hospital_id):

    try:

        appointments = (
            get_hospital_appointments(
                hospital_id
            )
        )

        locations = Counter()

        for appointment in appointments:

            location = (
                appointment.get(
                    "village"
                )
                or
                appointment.get(
                    "address"
                )
                or
                "Unknown"
            )

            location = str(
                location
            ).strip()

            if not location:
                location = "Unknown"

            locations[location] += 1

        return jsonify({

            "success":
                True,

            "data":
                dict(
                    locations.most_common()
                )
        })

    except Exception as e:

        traceback.print_exc()

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# APPOINTMENTS LIST
# ============================================================

@app.route(
    "/appointments/<uid>"
)
def appointments(uid):

    patients = (
        get_hospital_appointments(
            uid
        )
    )

    return render_template(

        "appointments.html",

        patients=patients,

        uid=uid
    )


# ============================================================
# FOLLOW-UP LIST
# ============================================================

@app.route(
    "/followups/<uid>"
)
def followups(uid):

    patients = (
        get_hospital_appointments(
            uid
        )
    )

    return render_template(

        "followups.html",

        patients=patients,

        uid=uid
    )


# ============================================================
# SAVE FOLLOW-UP
# ============================================================

@app.route(
    "/save_followup",
    methods=["POST"]
)
def save_followup():

    try:

        patient_id = request.form.get(
            "patient_id"
        )

        next_visit_date = request.form.get(
            "next_visit_date"
        )

        doctor_notes = request.form.get(
            "doctor_notes"
        )

        if not patient_id:

            return jsonify({

                "success":
                    False,

                "error":
                    "Patient ID missing"

            }), 400

        patient_ref = (
            db.reference("appointments")
            .child(patient_id)
        )

        patient = patient_ref.get()

        if not patient:

            return jsonify({

                "success":
                    False,

                "error":
                    "Patient not found"

            }), 404

        patient_ref.update({

            "next_visit_date":
                next_visit_date,

            "doctor_notes":
                doctor_notes,

            "followup_created_at":
                utc_now().isoformat()
        })

        fcm_result = send_notification(
            patient_id
        )

        whatsapp_result = (
            send_whatsapp_followup(
                patient_id
            )
        )

        return jsonify({

            "success":
                True,

            "message":
                "Follow-up Saved",

            "notification":
                fcm_result,

            "whatsapp":
                whatsapp_result
        })

    except Exception as e:

        print(
            "SAVE FOLLOWUP ERROR:",
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
# SAVE FCM TOKEN
# ============================================================

@app.route(
    "/save_token",
    methods=["POST"]
)
def save_token():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        token = data.get(
            "token"
        )

        patient_id = data.get(
            "patient_id"
        )

        if not token or not patient_id:

            return jsonify({

                "success":
                    False,

                "error":
                    "Token or Patient ID missing"

            }), 400

        db.reference(
            f"notification_tokens/{patient_id}"
        ).set({

            "token":
                token
        })

        return jsonify({

            "success":
                True,

            "message":
                "Token saved"
        })

    except Exception as e:

        print(
            "SAVE TOKEN ERROR:",
            str(e)
        )

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# FCM NOTIFICATION
# ============================================================

def send_notification(patient_id):

    try:

        patient = (
            db.reference(
                "appointments"
            )
            .child(patient_id)
            .get()
        )

        token_data = (
            db.reference(
                "notification_tokens"
            )
            .child(patient_id)
            .get()
        )

        if not patient:
            return "Patient not found"

        if not token_data:
            return "No token found"

        token = token_data.get(
            "token"
        )

        if not token:
            return "Token missing"

        patient_name = patient.get(
            "patient_name",
            "Patient"
        )

        visit_date = patient.get(
            "next_visit_date",
            ""
        )

        body = (
            f"{patient_name}, "
            f"your next visit is on "
            f"{visit_date}"
        )

        message = messaging.Message(

            token=token,

            notification=
                messaging.Notification(

                    title=
                        "Hospital Reminder",

                    body=
                        body
                ),

            webpush=
                messaging.WebpushConfig(

                    headers={
                        "Urgency":
                            "high"
                    },

                    notification=
                        messaging.WebpushNotification(

                            title=
                                "Hospital Reminder",

                            body=
                                body,

                            icon=
                                "/static/icon.png"
                        )
                )
        )

        response = messaging.send(
            message
        )

        print(
            "FCM SUCCESS:",
            response
        )

        return response

    except Exception as e:

        error = str(e)

        print(
            "FCM ERROR:",
            error
        )

        if (
            "UNREGISTERED" in error
            or
            "Device unregistered" in error
        ):

            db.reference(
                "notification_tokens"
            ).child(
                patient_id
            ).delete()

            return "Old token deleted"

        traceback.print_exc()

        return error


# ============================================================
# AISENSY APPOINTMENT CONFIRMATION
# ============================================================

def send_aisensy_appointment_confirmation(
    patient_id
):

    patient = (
        db.reference(
            "appointments"
        )
        .child(patient_id)
        .get()
    )

    if not patient:

        return {
            "success": False,
            "error": "Patient not found"
        }

    mobile = patient.get(
        "mobile"
    )

    if not mobile:

        return {
            "success": False,
            "error": "Patient mobile number missing"
        }

    recipient = format_whatsapp_number(
        mobile
    )

    if not recipient:

        return {
            "success": False,
            "error": "Invalid mobile number"
        }

    if not AISENSY_API_KEY:

        return {
            "success": False,
            "error": "AISENSY_API_KEY is missing"
        }

    hospital_id = patient.get(
        "hospital_id"
    )

    hospital = (
        db.reference(
            f"hospitals/{hospital_id}"
        ).get()
        or {}
    )

    hospital_name = hospital.get(
        "hospital_name",
        "MediQueue Hospital"
    )

    patient_name = patient.get(
        "patient_name",
        "Patient"
    )

    doctor_name = patient.get(
        "doctor_name",
        "Doctor"
    )

    appointment_date = patient.get(
        "appointment_date",
        ""
    )

    appointment_time = patient.get(
        "appointment_time",
        ""
    )

    payload = {

        "apiKey":
            AISENSY_API_KEY,

        "campaignName":
            AISENSY_APPOINTMENT_CAMPAIGN,

        "destination":
            recipient,

        "userName":
            patient_name,

        "templateParams": [

            patient_name,

            hospital_name,

            doctor_name,

            appointment_date,

            appointment_time,

            patient_id
        ]
    }

    try:

        response = requests.post(

            AISENSY_API_URL,

            json=payload,

            timeout=30
        )

        print(
            "AISENSY APPOINTMENT:",
            response.status_code,
            response.text
        )

        return {

            "success":
                response.ok,

            "status":
                response.status_code,

            "response":
                response.text
        }

    except Exception as e:

        print(
            "AISENSY APPOINTMENT ERROR:",
            str(e)
        )

        return {

            "success":
                False,

            "error":
                str(e)
        }


# ============================================================
# AISENSY FOLLOW-UP
# ============================================================

def send_whatsapp_followup(patient_id):

    patient = (
        db.reference(
            "appointments"
        )
        .child(patient_id)
        .get()
    )

    if not patient:

        return {
            "success": False,
            "error": "Patient not found"
        }

    mobile = patient.get(
        "mobile"
    )

    if not mobile:

        return {
            "success": False,
            "error": "Patient mobile number missing"
        }

    recipient = format_whatsapp_number(
        mobile
    )

    if not recipient:

        return {
            "success": False,
            "error": "Invalid mobile number"
        }

    if not AISENSY_API_KEY:

        return {
            "success": False,
            "error": "AISENSY_API_KEY is missing"
        }

    hospital_id = patient.get(
        "hospital_id"
    )

    hospital = (
        db.reference(
            f"hospitals/{hospital_id}"
        ).get()
        or {}
    )

    hospital_name = hospital.get(
        "hospital_name",
        "MediQueue Hospital"
    )

    patient_name = patient.get(
        "patient_name",
        "Patient"
    )

    doctor_name = patient.get(
        "doctor_name",
        "Doctor"
    )

    next_visit_date = patient.get(
        "next_visit_date",
        ""
    )

    payload = {

        "apiKey":
            AISENSY_API_KEY,

        "campaignName":
            AISENSY_FOLLOWUP_CAMPAIGN,

        "destination":
            recipient,

        "userName":
            patient_name,

        "templateParams": [

            patient_name,

            hospital_name,

            doctor_name,

            next_visit_date
        ]
    }

    try:

        response = requests.post(

            AISENSY_API_URL,

            json=payload,

            timeout=30
        )

        print(
            "AISENSY FOLLOW-UP:",
            response.status_code,
            response.text
        )

        return {

            "success":
                response.ok,

            "status":
                response.status_code,

            "response":
                response.text
        }

    except Exception as e:

        print(
            "AISENSY FOLLOW-UP ERROR:",
            str(e)
        )

        return {

            "success":
                False,

            "error":
                str(e)
        }


# ============================================================
# WHATSAPP WEBHOOK
# ============================================================

@app.route(
    "/webhook",
    methods=["GET", "POST", "HEAD"]
)
def whatsapp_webhook():

    if request.method == "HEAD":
        return "", 200

    if request.method == "GET":

        mode = request.args.get(
            "hub.mode"
        )

        token = request.args.get(
            "hub.verify_token"
        )

        challenge = request.args.get(
            "hub.challenge"
        )

        if (
            mode == "subscribe"
            and
            token == "mediqueue_webhook_2026"
            and
            challenge
        ):

            return challenge, 200

        return (
            "Verification failed",
            403
        )

    data = request.get_json(
        silent=True
    )

    print(
        "WHATSAPP WEBHOOK:",
        data
    )

    return "EVENT_RECEIVED", 200


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )
