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
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

CORS(app)


# ============================================================
# FIREBASE CONFIGURATION
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
# AISENSY CONFIGURATION
# ============================================================

AISENSY_API_KEY = os.environ.get(
    "AISENSY_API_KEY",
    ""
).strip()

AISENSY_API_URL = (
    "https://backend.aisensy.com/"
    "campaign/t1/api/v2"
)

AISENSY_APPOINTMENT_CAMPAIGN = (
    "MediQueue Appointment Confirmation"
)

AISENSY_FOLLOWUP_CAMPAIGN = (
    "mediqueue_followup_reminder"
)


# ============================================================
# CASHFREE CONFIGURATION
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


# ============================================================
# STATUSLY
# ============================================================

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
# UTILITY
# ============================================================

def format_whatsapp_number(mobile):

    if not mobile:
        return ""

    mobile = str(mobile).strip()

    mobile = "".join(
        filter(
            str.isdigit,
            mobile
        )
    )

    if len(mobile) == 10:
        mobile = "91" + mobile

    return mobile


# ============================================================
# FIREBASE AUTHENTICATION
# ============================================================

def get_authenticated_user():

    authorization = request.headers.get(
        "Authorization",
        ""
    ).strip()

    print(
        "AUTHORIZATION HEADER:",
        (
            authorization[:30] + "..."
            if authorization
            else "MISSING"
        )
    )

    if not authorization:

        print(
            "AUTH ERROR: Authorization header missing"
        )

        return None

    if not authorization.startswith("Bearer "):

        print(
            "AUTH ERROR: Invalid Authorization format"
        )

        return None

    token = authorization[7:].strip()

    if not token:

        print(
            "AUTH ERROR: Firebase token missing"
        )

        return None

    try:

        decoded = auth.verify_id_token(
            token
        )

        print(
            "FIREBASE TOKEN VERIFIED"
        )

        print(
            "FIREBASE UID:",
            decoded.get("uid")
        )

        print(
            "FIREBASE EMAIL:",
            decoded.get("email")
        )

        return decoded

    except Exception as e:

        print(
            "FIREBASE AUTH ERROR:",
            str(e)
        )

        traceback.print_exc()

        return None


# ============================================================
# SUBSCRIPTION HELPERS
# ============================================================

def get_subscription(uid):

    if not uid:
        return None

    return db.reference(
        "subscriptions"
    ).child(
        uid
    ).get()


def subscription_is_active(uid):

    if not uid:
        return False

    subscription = get_subscription(uid)

    if not subscription:

        print(
            "NO SUBSCRIPTION FOUND FOR UID:",
            uid
        )

        return False

    payment_status = subscription.get(
        "payment_status",
        ""
    )

    print(
        "PAYMENT STATUS:",
        payment_status
    )

    if payment_status != "PAID":

        return False

    expiry_string = subscription.get(
        "expiry"
    )

    if not expiry_string:

        print(
            "SUBSCRIPTION EXPIRY MISSING"
        )

        return False

    try:

        expiry = datetime.fromisoformat(
            expiry_string
        )

        now = datetime.utcnow()

        print(
            "CURRENT UTC:",
            now
        )

        print(
            "SUBSCRIPTION EXPIRY:",
            expiry
        )

        return now < expiry

    except Exception as e:

        print(
            "SUBSCRIPTION EXPIRY ERROR:",
            str(e)
        )

        return False


# ============================================================
# CASHFREE HEADERS
# ============================================================

def cashfree_headers():

    return {

        "x-client-id":
            CASHFREE_CLIENT_ID,

        "x-client-secret":
            CASHFREE_CLIENT_SECRET,

        "x-api-version":
            CASHFREE_API_VERSION,

        "Content-Type":
            "application/json",

        "Accept":
            "application/json"

    }


# ============================================================
# FIREBASE SERVICE WORKER
# ============================================================

@app.route("/firebase-messaging-sw.js")
def firebase_sw():

    print(
        "SERVICE WORKER REQUESTED"
    )

    return send_from_directory(
        "static",
        "firebase-messaging-sw.js"
    )


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
# LOGIN API
# ============================================================

@app.route(
    "/login",
    methods=["POST"]
)
def login():

    try:

        decoded = get_authenticated_user()

        if not decoded:

            return jsonify({
                "success": False,
                "error": "Authentication required"
            }), 401

        uid = decoded.get("uid")

        hospital = db.reference(
            f"hospitals/{uid}"
        ).get() or {}

        return jsonify({

            "success": True,

            "uid":
                uid,

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

        print(
            "LOGIN ERROR:",
            str(e)
        )

        traceback.print_exc()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 401


# ============================================================
# TEMP DASHBOARD
# ============================================================

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
# PAYMENT PAGE
# ============================================================

@app.route("/payment")
def payment():

    return render_template(
        "payment.html"
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
# CREATE CASHFREE PAYMENT ORDER
# ============================================================

@app.route(
    "/create-payment-order",
    methods=["POST"]
)
def create_payment_order():

    try:

        print("=" * 60)
        print("CREATE PAYMENT ORDER")
        print("=" * 60)

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

        customer_name = str(
            data.get(
                "customer_name",
                "Statusly Customer"
            )
        ).strip()

        customer_email = str(
            data.get(
                "customer_email",
                decoded.get("email", "")
            )
        ).strip()

        customer_phone = str(
            data.get(
                "customer_phone",
                ""
            )
        )

        if plan not in PLANS:

            return jsonify({
                "success": False,
                "error": "Invalid plan"
            }), 400

        plan_data = PLANS[plan]

        amount = plan_data["amount"]

        duration_days = plan_data[
            "duration_days"
        ]

        if not CASHFREE_CLIENT_ID:

            return jsonify({
                "success": False,
                "error":
                    "CASHFREE_CLIENT_ID is missing"
            }), 500

        if not CASHFREE_CLIENT_SECRET:

            return jsonify({
                "success": False,
                "error":
                    "CASHFREE_CLIENT_SECRET is missing"
            }), 500

        customer_phone = "".join(
            filter(
                str.isdigit,
                customer_phone
            )
        )

        if len(customer_phone) == 12:
            customer_phone = customer_phone[-10:]

        if len(customer_phone) != 10:

            return jsonify({
                "success": False,
                "error":
                    "Valid 10 digit customer phone is required"
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
                    (
                        customer_email
                        or
                        f"{uid}@statusly.in"
                    ),

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

        print(
            "ORDER ID:",
            order_id
        )

        response = requests.post(

            f"{CASHFREE_BASE_URL}/orders",

            headers=cashfree_headers(),

            json=payload,

            timeout=30

        )

        print(
            "CASHFREE STATUS:",
            response.status_code
        )

        print(
            "CASHFREE RESPONSE:",
            response.text
        )

        if not response.ok:

            return jsonify({

                "success":
                    False,

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

                "success":
                    False,

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
                datetime.utcnow().isoformat()

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

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# ACTIVATE SUBSCRIPTION
# ============================================================

def activate_subscription(order_id):

    try:

        payment_ref = db.reference(
            "payment_orders"
        ).child(
            order_id
        )

        payment_order = payment_ref.get()

        if not payment_order:

            return {
                "success": False,
                "error":
                    "Local payment order not found"
            }

        if payment_order.get(
            "subscription_activated"
        ):

            return {
                "success": True,
                "already_activated": True
            }

        uid = payment_order.get(
            "uid"
        )

        plan = payment_order.get(
            "plan"
        )

        amount = payment_order.get(
            "amount"
        )

        duration_days = payment_order.get(
            "duration_days"
        )

        if not uid:

            return {
                "success": False,
                "error": "UID missing"
            }

        if not plan:

            return {
                "success": False,
                "error": "Plan missing"
            }

        expiry = (
            datetime.utcnow()
            +
            timedelta(
                days=int(duration_days)
            )
        )

        payment_id = ""

        try:

            response = requests.get(

                f"{CASHFREE_BASE_URL}"
                f"/orders/{order_id}/payments",

                headers=cashfree_headers(),

                timeout=30

            )

            print(
                "Cashfree Payments Response:",
                response.status_code,
                response.text
            )

            if response.ok:

                payments = response.json()

                if isinstance(
                    payments,
                    list
                ):

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
                "PAYMENT ID FETCH ERROR:",
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
                datetime.utcnow().isoformat()

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
                datetime.utcnow().isoformat()

        })

        print(
            "SUBSCRIPTION ACTIVATED:",
            uid
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

        local_order = db.reference(
            "payment_orders"
        ).child(
            order_id
        ).get()

        if not local_order:

            return jsonify({

                "success":
                    False,

                "error":
                    "Local payment order not found"

            }), 404

        response = requests.get(

            f"{CASHFREE_BASE_URL}"
            f"/orders/{order_id}",

            headers=cashfree_headers(),

            timeout=30

        )

        print(
            "CASHFREE ORDER STATUS:",
            response.status_code
        )

        print(
            "CASHFREE RESPONSE:",
            response.text
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

        cashfree_status = cashfree_order.get(
            "order_status"
        )

        if cashfree_status == "PAID":

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
                cashfree_status or "UNKNOWN",

            "last_checked_at":
                datetime.utcnow().isoformat()

        })

        return jsonify({

            "success":
                True,

            "paid":
                False,

            "order_id":
                order_id,

            "order_status":
                cashfree_status

        })

    except Exception as e:

        print(
            "CASHFREE ORDER STATUS ERROR:",
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
            "========== CASHFREE WEBHOOK =========="
        )

        print(data)

        order_id = (
            data
            .get("data", {})
            .get("order", {})
            .get("order_id")
        )

        if order_id:

            try:

                response = requests.get(

                    f"{CASHFREE_BASE_URL}"
                    f"/orders/{order_id}",

                    headers=cashfree_headers(),

                    timeout=30

                )

                if response.ok:

                    order_data = response.json()

                    status = order_data.get(
                        "order_status"
                    )

                    if status == "PAID":

                        activate_subscription(
                            order_id
                        )

            except Exception as e:

                print(
                    "WEBHOOK VERIFICATION ERROR:",
                    str(e)
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

        uid = decoded.get(
            "uid"
        )

        if not uid:

            return jsonify({

                "success":
                    False,

                "error":
                    "UID missing"

            }), 400

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

        uid = request.form.get(
            "uid"
        )

        if not uid:

            return jsonify({
                "error": "UID missing"
            }), 400

        subscription = get_subscription(
            uid
        )

        if not subscription:

            return jsonify({

                "error":
                    "Active subscription required"

            }), 403

        if not subscription_is_active(
            uid
        ):

            return jsonify({

                "error":
                    "Subscription expired or inactive"

            }), 403

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

        count = min(
            len(names),
            len(specs),
            len(times),
            len(infos)
        )

        for i in range(count):

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
                datetime.utcnow().isoformat(),

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
                "Saved",

            "uid":
                uid,

            # IMPORTANT:
            # Correct hospital URL
            "hospital_url":
                f"/hospital/{uid}",

            "booking_url":
                f"/hospital/{uid}/book"

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
# IMPORTANT:
#
# Correct:
# /hospital/<uid>
#
# Example:
# /hospital/r6ZBUzipweW9LhEcmgZ3dGWcMrS2
#
# NOT:
# /hospitalr6ZBUzipweW9LhEcmgZ3dGWcMrS2
# ============================================================

@app.route(
    "/hospital/<uid>",
    methods=["GET"]
)
def hospital_page(uid):

    print(
        "HOSPITAL PAGE REQUEST:",
        uid
    )

    data = db.reference(
        f"hospitals/{uid}"
    ).get()

    if not data:

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

        hospital=data,

        uid=uid

    )


# ============================================================
# BOOK PAGE
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
        f"hospitals/{uid}"
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

        fcm_token = request.form.get(
            "fcm_token"
        )

        if not hospital_id:

            return jsonify({

                "success":
                    False,

                "error":
                    "Hospital ID missing"

            }), 400

        hospital = db.reference(
            f"hospitals/{hospital_id}"
        ).get()

        if not hospital:

            return jsonify({

                "success":
                    False,

                "error":
                    "Hospital not found"

            }), 404

        counter_ref = db.reference(
            "counters/patient_no"
        )

        current_number = (
            counter_ref.get()
            or 0
        )

        patient_no = (
            int(current_number)
            + 1
        )

        counter_ref.set(
            patient_no
        )

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
                datetime.utcnow().isoformat()

        }

        ref = db.reference(
            "appointments"
        ).push(
            appointment
        )

        patient_id = ref.key

        if fcm_token:

            db.reference(
                "notification_tokens"
            ).child(
                patient_id
            ).set({

                "token":
                    fcm_token

            })

        whatsapp_result = (
            send_aisensy_appointment_confirmation(
                patient_id
            )
        )

        hospital_name = hospital.get(
            "hospital_name",
            "Hospital"
        )

        doctor_name = appointment.get(
            "doctor_name",
            "Doctor"
        )

        appointment_date = appointment.get(
            "appointment_date",
            ""
        )

        appointment_time = appointment.get(
            "appointment_time",
            ""
        )

        specialization = ""

        for doctor in hospital.get(
            "doctors",
            []
        ):

            if (
                doctor.get("doctor_name")
                ==
                doctor_name
            ):

                specialization = doctor.get(
                    "specialization",
                    ""
                )

                break

        return render_template(

            "success.html",

            patient_id=
                patient_id,

            hospital_name=
                hospital_name,

            doctor_name=
                doctor_name,

            specialization=
                specialization,

            appointment_date=
                appointment_date,

            appointment_time=
                appointment_time,

            whatsapp=
                whatsapp_result

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
# APPOINTMENTS LIST
# ============================================================

@app.route(
    "/appointments/<uid>",
    methods=["GET"]
)
def appointments(uid):

    data = db.reference(
        "appointments"
    ).get() or {}

    patients = []

    for key, patient in data.items():

        if patient.get(
            "hospital_id"
        ) != uid:

            continue

        patient = dict(
            patient
        )

        patient["id"] = key

        patients.append(
            patient
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
    "/followups/<uid>",
    methods=["GET"]
)
def followups(uid):

    data = db.reference(
        "appointments"
    ).get() or {}

    patients = []

    for key, patient in data.items():

        if patient.get(
            "hospital_id"
        ) != uid:

            continue

        patient = dict(
            patient
        )

        patient["id"] = key

        patients.append(
            patient
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

        patient_ref = db.reference(
            "appointments"
        ).child(
            patient_id
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
                datetime.utcnow().isoformat()

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
            "notification_tokens"
        ).child(
            patient_id
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

        patient = db.reference(
            "appointments"
        ).child(
            patient_id
        ).get()

        token_data = db.reference(
            "notification_tokens"
        ).child(
            patient_id
        ).get()

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

        notification_body = (
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
                        notification_body

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
                                notification_body,

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
# AISENSY APPOINTMENT
# ============================================================

def send_aisensy_appointment_confirmation(
    patient_id
):

    try:

        patient = db.reference(
            "appointments"
        ).child(
            patient_id
        ).get()

        if not patient:

            return {

                "success":
                    False,

                "error":
                    "Patient not found"

            }

        mobile = patient.get(
            "mobile"
        )

        if not mobile:

            return {

                "success":
                    False,

                "error":
                    "Patient mobile number missing"

            }

        recipient = format_whatsapp_number(
            mobile
        )

        if not recipient:

            return {

                "success":
                    False,

                "error":
                    "Invalid mobile number"

            }

        hospital_id = patient.get(
            "hospital_id"
        )

        hospital = db.reference(
            f"hospitals/{hospital_id}"
        ).get() or {}

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

        if not AISENSY_API_KEY:

            return {

                "success":
                    False,

                "error":
                    "AISENSY_API_KEY is missing"

            }

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

        if response.ok:

            return {

                "success":
                    True,

                "status":
                    response.status_code,

                "response":
                    response.text

            }

        return {

            "success":
                False,

            "status":
                response.status_code,

            "error":
                response.text

        }

    except Exception as e:

        print(
            "AISENSY APPOINTMENT ERROR:",
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
# AISENSY FOLLOW-UP
# ============================================================

def send_whatsapp_followup(patient_id):

    try:

        patient = db.reference(
            "appointments"
        ).child(
            patient_id
        ).get()

        if not patient:

            return {

                "success":
                    False,

                "error":
                    "Patient not found"

            }

        mobile = patient.get(
            "mobile"
        )

        if not mobile:

            return {

                "success":
                    False,

                "error":
                    "Patient mobile number missing"

            }

        recipient = format_whatsapp_number(
            mobile
        )

        if not recipient:

            return {

                "success":
                    False,

                "error":
                    "Invalid mobile number"

            }

        hospital_id = patient.get(
            "hospital_id"
        )

        hospital = db.reference(
            f"hospitals/{hospital_id}"
        ).get() or {}

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

        if not AISENSY_API_KEY:

            return {

                "success":
                    False,

                "error":
                    "AISENSY_API_KEY is missing"

            }

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

        if response.ok:

            return {

                "success":
                    True,

                "status":
                    response.status_code,

                "response":
                    response.text

            }

        return {

            "success":
                False,

            "status":
                response.status_code,

            "error":
                response.text

        }

    except Exception as e:

        print(
            "AISENSY FOLLOW-UP ERROR:",
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
# WHATSAPP WEBHOOK
# ============================================================

@app.route(
    "/webhook",
    methods=[
        "GET",
        "POST",
        "HEAD"
    ]
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

        print(
            "META WEBHOOK VERIFICATION"
        )

        if (

            mode == "subscribe"

            and

            token ==
            "mediqueue_webhook_2026"

            and

            challenge

        ):

            return challenge, 200

        return (
            "Verification failed",
            403
        )

    if request.method == "POST":

        data = request.get_json(
            silent=True
        )

        print(
            "WHATSAPP WEBHOOK EVENT:",
            data
        )

        return (
            "EVENT_RECEIVED",
            200
        )


# ============================================================
# HEALTH CHECK
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
