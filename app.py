from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_from_directory
)

import json
import os
import uuid
import hmac
import hashlib
import base64
import traceback
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
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

CORS(app)


# ============================================================
# ENVIRONMENT HELPERS
# ============================================================

def env_required(name):
    value = os.environ.get(name, "").strip()

    if not value:
        raise RuntimeError(
            f"{name} environment variable is missing"
        )

    return value


# ============================================================
# FIREBASE CONFIGURATION
# ============================================================

FIREBASE_SERVICE_ACCOUNT = env_required(
    "FIREBASE_SERVICE_ACCOUNT"
)

try:
    firebase_service_account = json.loads(
        FIREBASE_SERVICE_ACCOUNT
    )
except json.JSONDecodeError as e:
    raise RuntimeError(
        f"FIREBASE_SERVICE_ACCOUNT contains invalid JSON: {e}"
    )


FIREBASE_DATABASE_URL = os.environ.get(
    "FIREBASE_DATABASE_URL",
    "https://hospital-57fc8-default-rtdb.firebaseio.com"
).strip()


if not firebase_admin._apps:

    cred = credentials.Certificate(
        firebase_service_account
    )

    firebase_admin.initialize_app(
        cred,
        {
            "databaseURL": FIREBASE_DATABASE_URL
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

AISENSY_APPOINTMENT_CAMPAIGN = os.environ.get(
    "AISENSY_APPOINTMENT_CAMPAIGN",
    "MediQueue Appointment Confirmation"
).strip()

AISENSY_FOLLOWUP_CAMPAIGN = os.environ.get(
    "AISENSY_FOLLOWUP_CAMPAIGN",
    "mediqueue_followup_reminder"
).strip()


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
# APPLICATION URL
# ============================================================

STATUSLY_BASE_URL = os.environ.get(
    "STATUSLY_BASE_URL",
    "https://statusly.in"
).strip().rstrip("/")


# ============================================================
# META / WHATSAPP WEBHOOK
# ============================================================

WHATSAPP_VERIFY_TOKEN = os.environ.get(
    "WHATSAPP_VERIFY_TOKEN",
    "mediqueue_webhook_2026"
).strip()


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
# TIME HELPERS
# ============================================================

def utc_now():
    return datetime.utcnow()


def utc_iso():
    return utc_now().isoformat()


# ============================================================
# WHATSAPP NUMBER
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

    elif len(mobile) == 12 and mobile.startswith("91"):
        pass

    else:
        return ""

    return mobile


# ============================================================
# AUTHENTICATION
# ============================================================

def get_authenticated_user():

    authorization = request.headers.get(
        "Authorization",
        ""
    ).strip()

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
            "FIREBASE TOKEN VERIFIED:",
            decoded.get("uid")
        )

        return decoded

    except Exception as e:

        print(
            "FIREBASE AUTH ERROR:",
            str(e)
        )

        return None


# ============================================================
# REQUIRE AUTHENTICATION
# ============================================================

def require_authenticated_user():

    decoded = get_authenticated_user()

    if not decoded:
        return None

    return decoded


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
# PAYMENT PAGE
# ============================================================

@app.route("/payment")
def payment():

    return render_template(
        "payment.html"
    )


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
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    return render_template(
        "dashboard.html"
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

        decoded = require_authenticated_user()

        if not decoded:

            return jsonify({
                "success": False,
                "error": "Invalid Firebase token"
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
            "error": "Authentication failed"
        }), 401


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
# CASHFREE CONFIG CHECK
# ============================================================

def cashfree_configured():

    return bool(
        CASHFREE_CLIENT_ID
        and
        CASHFREE_CLIENT_SECRET
    )


# ============================================================
# GET SUBSCRIPTION
# ============================================================

def get_subscription(uid):

    if not uid:
        return None

    return (
        db.reference(
            "subscriptions"
        )
        .child(uid)
        .get()
    )


# ============================================================
# CHECK SUBSCRIPTION ACTIVE
# ============================================================

def subscription_is_active(uid):

    subscription = get_subscription(uid)

    if not subscription:
        return False

    if subscription.get(
        "payment_status"
    ) != "PAID":

        return False

    expiry_string = subscription.get(
        "expiry"
    )

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
# ACTIVATE SUBSCRIPTION
# ============================================================

def activate_subscription(order_id):

    try:

        payment_ref = (
            db.reference(
                "payment_orders"
            )
            .child(order_id)
        )

        payment_order = payment_ref.get()

        if not payment_order:

            return {
                "success": False,
                "error":
                    "Local payment order not found"
            }

        # ----------------------------------------------------
        # IDEMPOTENCY
        # ----------------------------------------------------

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

        if plan not in PLANS:
            return {
                "success": False,
                "error": "Invalid plan"
            }

        duration_days = int(
            duration_days
        )

        # ----------------------------------------------------
        # EXPIRY
        # ----------------------------------------------------

        expiry = (
            utc_now()
            + timedelta(
                days=duration_days
            )
        )

        # ----------------------------------------------------
        # GET SUCCESSFUL PAYMENT
        # ----------------------------------------------------

        payment_id = ""

        try:

            response = requests.get(

                f"{CASHFREE_BASE_URL}/orders/"
                f"{order_id}/payments",

                headers=cashfree_headers(),

                timeout=30

            )

            print(
                "CASHFREE PAYMENTS:",
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

                            payment_id = str(
                                payment.get(
                                    "cf_payment_id",
                                    ""
                                )
                            )

                            break

        except Exception as e:

            print(
                "PAYMENT ID FETCH ERROR:",
                str(e)
            )

        # ----------------------------------------------------
        # SAVE SUBSCRIPTION
        # ----------------------------------------------------

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
                utc_iso()

        }

        (
            db.reference(
                "subscriptions"
            )
            .child(uid)
            .set(subscription_data)
        )

        # ----------------------------------------------------
        # MARK ORDER ACTIVATED
        # ----------------------------------------------------

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
                utc_iso()

        })

        print(
            "SUBSCRIPTION ACTIVATED:",
            order_id
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
# CREATE CASHFREE PAYMENT ORDER
# ============================================================

@app.route(
    "/create-payment-order",
    methods=["POST"]
)
def create_payment_order():

    try:

        decoded = require_authenticated_user()

        if not decoded:

            return jsonify({

                "success": False,

                "error":
                    "Authentication required"

            }), 401

        uid = decoded.get("uid")

        if not uid:

            return jsonify({

                "success": False,

                "error":
                    "UID missing"

            }), 400

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        plan = str(
            data.get(
                "plan",
                "basic"
            )
        ).lower().strip()

        if plan not in PLANS:

            return jsonify({

                "success": False,

                "error":
                    "Invalid plan"

            }), 400

        if not cashfree_configured():

            return jsonify({

                "success": False,

                "error":
                    "Cashfree configuration missing"

            }), 500

        plan_data = PLANS[plan]

        amount = float(
            plan_data["amount"]
        )

        duration_days = int(
            plan_data["duration_days"]
        )

        # ----------------------------------------------------
        # CUSTOMER
        # ----------------------------------------------------

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

        customer_phone = "".join(
            filter(
                str.isdigit,
                customer_phone
            )
        )

        if len(customer_phone) == 12:

            if customer_phone.startswith("91"):
                customer_phone = customer_phone[2:]

        if len(customer_phone) != 10:

            return jsonify({

                "success": False,

                "error":
                    "Valid 10 digit customer phone is required"

            }), 400

        if not customer_email:

            customer_email = (
                f"{uid}@statusly.in"
            )

        # ----------------------------------------------------
        # ORDER ID
        # ----------------------------------------------------

        order_id = (
            "STATUSLY_"
            + uuid.uuid4().hex
        )

        # ----------------------------------------------------
        # RETURN URL
        # ----------------------------------------------------

        return_url = (
            f"{STATUSLY_BASE_URL}"
            f"/temp-dash"
            f"?order_id={order_id}"
        )

        # ----------------------------------------------------
        # CASHFREE PAYLOAD
        # ----------------------------------------------------

        payload = {

            "order_id":
                order_id,

            "order_amount":
                amount,

            "order_currency":
                "INR",

            "customer_details": {

                "customer_id":
                    uid,

                "customer_name":
                    customer_name,

                "customer_email":
                    customer_email,

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

        response = requests.post(

            f"{CASHFREE_BASE_URL}/orders",

            headers={
                **cashfree_headers(),
                "x-request-id":
                    str(uuid.uuid4()),
                "x-idempotency-key":
                    str(uuid.uuid4())
            },

            json=payload,

            timeout=30

        )

        print(
            "CASHFREE CREATE ORDER:",
            response.status_code
        )

        print(
            "CASHFREE RESPONSE:",
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

        # ----------------------------------------------------
        # SAVE LOCAL ORDER
        # ----------------------------------------------------

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
                utc_iso()

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

        }), 200

    except Exception as e:

        print(
            "CREATE PAYMENT ORDER ERROR:",
            str(e)
        )

        traceback.print_exc()

        return jsonify({

            "success": False,

            "error":
                str(e)

        }), 500


# ============================================================
# CASHFREE ORDER STATUS
# ============================================================

@app.route(
    "/cashfree/order-status/<order_id>",
    methods=["GET"]
)
def cashfree_order_status(order_id):

    try:

        decoded = require_authenticated_user()

        if not decoded:

            return jsonify({
                "success": False,
                "error": "Authentication required"
            }), 401

        uid = decoded.get("uid")

        local_order = (
            db.reference(
                "payment_orders"
            )
            .child(order_id)
            .get()
        )

        if not local_order:

            return jsonify({

                "success": False,

                "error":
                    "Local payment order not found"

            }), 404

        # ----------------------------------------------------
        # SECURITY: ORDER MUST BELONG TO USER
        # ----------------------------------------------------

        if local_order.get("uid") != uid:

            return jsonify({

                "success": False,

                "error":
                    "Unauthorized order"

            }), 403

        response = requests.get(

            f"{CASHFREE_BASE_URL}/orders/"
            f"{order_id}",

            headers=cashfree_headers(),

            timeout=30

        )

        print(
            "CASHFREE ORDER STATUS:",
            response.status_code,
            response.text
        )

        if not response.ok:

            return jsonify({

                "success": False,

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

            activation = (
                activate_subscription(
                    order_id
                )
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
                utc_iso()

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
# CASHFREE WEBHOOK SIGNATURE
# ============================================================

def verify_cashfree_webhook():

    signature = request.headers.get(
        "x-webhook-signature",
        ""
    ).strip()

    timestamp = request.headers.get(
        "x-webhook-timestamp",
        ""
    ).strip()

    if not signature or not timestamp:

        return False

    if not CASHFREE_CLIENT_SECRET:

        return False

    raw_body = request.get_data(
        cache=True,
        as_text=True
    )

    signed_payload = (
        timestamp + raw_body
    )

    expected_signature = base64.b64encode(

        hmac.new(

            CASHFREE_CLIENT_SECRET.encode(
                "utf-8"
            ),

            signed_payload.encode(
                "utf-8"
            ),

            hashlib.sha256

        ).digest()

    ).decode(
        "utf-8"
    )

    return hmac.compare_digest(
        expected_signature,
        signature
    )


# ============================================================
# CASHFREE WEBHOOK
# ============================================================

@app.route(
    "/cashfree/webhook",
    methods=["POST"]
)
def cashfree_webhook():

    try:

        # IMPORTANT:
        # Verify using raw body BEFORE parsing JSON.

        if not verify_cashfree_webhook():

            print(
                "CASHFREE WEBHOOK SIGNATURE INVALID"
            )

            return (
                "Invalid signature",
                401
            )

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

            return (
                "EVENT_RECEIVED",
                200
            )

        # ----------------------------------------------------
        # VERIFY WITH CASHFREE API
        # ----------------------------------------------------

        response = requests.get(

            f"{CASHFREE_BASE_URL}/orders/"
            f"{order_id}",

            headers=cashfree_headers(),

            timeout=30

        )

        if response.ok:

            order_data = response.json()

            status = order_data.get(
                "order_status"
            )

            print(
                "VERIFIED CASHFREE STATUS:",
                status
            )

            if status == "PAID":

                result = (
                    activate_subscription(
                        order_id
                    )
                )

                print(
                    "WEBHOOK ACTIVATION:",
                    result
                )

        return (
            "EVENT_RECEIVED",
            200
        )

    except Exception as e:

        print(
            "CASHFREE WEBHOOK ERROR:",
            str(e)
        )

        traceback.print_exc()

        return (
            "EVENT_RECEIVED",
            200
        )


# ============================================================
# CHECK SUBSCRIPTION
# ============================================================

@app.route(
    "/check-subscription",
    methods=["POST"]
)
def check_subscription():

    try:

        decoded = require_authenticated_user()

        if not decoded:

            return jsonify({

                "success": False,

                "error":
                    "Authentication required"

            }), 401

        uid = decoded.get("uid")

        if not uid:

            return jsonify({

                "success": False,

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

            "success": False,

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
        # AUTHENTICATE
        # ----------------------------------------------------

        decoded = require_authenticated_user()

        if not decoded:

            return jsonify({

                "success": False,

                "error":
                    "Authentication required"

            }), 401

        uid = decoded.get("uid")

        if not uid:

            return jsonify({
                "error": "UID missing"
            }), 400

        # ----------------------------------------------------
        # CHECK SUBSCRIPTION
        # ----------------------------------------------------

        if not subscription_is_active(uid):

            return jsonify({

                "success": False,

                "error":
                    "Active subscription required"

            }), 403

        # ----------------------------------------------------
        # FORM DATA
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

        doctor_count = min(
            len(names),
            len(specs),
            len(times),
            len(infos)
        )

        for i in range(
            doctor_count
        ):

            doctors.append({

                "doctor_name":
                    names[i].strip(),

                "specialization":
                    specs[i].strip(),

                "opd_time":
                    times[i].strip(),

                "doctor_info":
                    infos[i].strip()

            })

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
                ).strip(),

            "open_time":
                request.form.get(
                    "open_time",
                    ""
                ).strip(),

            "close_time":
                request.form.get(
                    "close_time",
                    ""
                ).strip(),

            "info":
                request.form.get(
                    "info",
                    ""
                ).strip(),

            "created_at":
                utc_iso(),

            "doctors":
                doctors

        }

        (
            db.reference(
                "hospitals"
            )
            .child(uid)
            .set(hospital_data)
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

            "success": False,

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
            "hospital_id",
            ""
        ).strip()

        fcm_token = request.form.get(
            "fcm_token",
            ""
        ).strip()

        if not hospital_id:

            return jsonify({

                "success": False,

                "error":
                    "Hospital ID missing"

            }), 400

        hospital = (
            db.reference(
                f"hospitals/{hospital_id}"
            ).get()
        )

        if not hospital:

            return jsonify({

                "success": False,

                "error":
                    "Hospital not found"

            }), 404

        # ----------------------------------------------------
        # PATIENT NUMBER
        # ----------------------------------------------------

        counter_ref = db.reference(
            "counters/patient_no"
        )

        patient_no = (
            counter_ref.get()
            or 0
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
                    "doctor_name",
                    ""
                ).strip(),

            "patient_name":
                request.form.get(
                    "patient_name",
                    ""
                ).strip(),

            "gender":
                request.form.get(
                    "gender",
                    ""
                ).strip(),

            "age":
                request.form.get(
                    "age",
                    ""
                ).strip(),

            "mobile":
                request.form.get(
                    "mobile",
                    ""
                ).strip(),

            "address":
                request.form.get(
                    "address",
                    ""
                ).strip(),

            "appointment_date":
                request.form.get(
                    "appointment_date",
                    ""
                ).strip(),

            "appointment_time":
                request.form.get(
                    "appointment_time",
                    ""
                ).strip(),

            "created_at":
                utc_iso()

        }

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        ref = (
            db.reference(
                "appointments"
            )
            .push(appointment)
        )

        patient_id = ref.key

        # ----------------------------------------------------
        # FCM TOKEN
        # ----------------------------------------------------

        if fcm_token:

            (
                db.reference(
                    "notification_tokens"
                )
                .child(patient_id)
                .set({
                    "token": fcm_token
                })
            )

        # ----------------------------------------------------
        # WHATSAPP
        # ----------------------------------------------------

        whatsapp_result = (
            send_aisensy_appointment_confirmation(
                patient_id
            )
        )

        # ----------------------------------------------------
        # DOCTOR SPECIALIZATION
        # ----------------------------------------------------

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

            if (
                doctor.get("doctor_name")
                == doctor_name
            ):

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
                ),

            whatsapp_result=
                whatsapp_result

        )

    except Exception as e:

        print(
            "BOOK APPOINTMENT ERROR:",
            str(e)
        )

        traceback.print_exc()

        return jsonify({

            "success": False,

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

    data = (
        db.reference(
            "appointments"
        ).get()
        or {}
    )

    patients = []

    for key, patient in data.items():

        if patient.get(
            "hospital_id"
        ) != uid:

            continue

        patient = dict(patient)

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
    "/followups/<uid>"
)
def followups(uid):

    data = (
        db.reference(
            "appointments"
        ).get()
        or {}
    )

    patients = []

    for key, patient in data.items():

        if patient.get(
            "hospital_id"
        ) != uid:

            continue

        patient = dict(patient)

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
            "patient_id",
            ""
        ).strip()

        next_visit_date = request.form.get(
            "next_visit_date",
            ""
        ).strip()

        doctor_notes = request.form.get(
            "doctor_notes",
            ""
        ).strip()

        if not patient_id:

            return jsonify({

                "success": False,

                "error":
                    "Patient ID missing"

            }), 400

        patient_ref = (
            db.reference(
                "appointments"
            )
            .child(patient_id)
        )

        patient = patient_ref.get()

        if not patient:

            return jsonify({

                "success": False,

                "error":
                    "Patient not found"

            }), 404

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        patient_ref.update({

            "next_visit_date":
                next_visit_date,

            "doctor_notes":
                doctor_notes,

            "followup_created_at":
                utc_iso()

        })

        # ----------------------------------------------------
        # FCM
        # ----------------------------------------------------

        fcm_result = send_notification(
            patient_id
        )

        # ----------------------------------------------------
        # WHATSAPP
        # ----------------------------------------------------

        whatsapp_result = (
            send_whatsapp_followup(
                patient_id
            )
        )

        return jsonify({

            "success":
                True,

            "message":
                "Follow-up saved",

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

            "success": False,

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

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        token = str(
            data.get(
                "token",
                ""
            )
        ).strip()

        patient_id = str(
            data.get(
                "patient_id",
                ""
            )
        ).strip()

        if not token or not patient_id:

            return jsonify({

                "success": False,

                "error":
                    "Token or Patient ID missing"

            }), 400

        (
            db.reference(
                "notification_tokens"
            )
            .child(patient_id)
            .set({
                "token": token
            })
        )

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

            "success": False,

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

        message_body = (
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
                        message_body

                ),

            webpush=
                messaging.WebpushConfig(

                    headers={
                        "Urgency": "high"
                    },

                    notification=
                        messaging.WebpushNotification(

                            title=
                                "Hospital Reminder",

                            body=
                                message_body,

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

            (
                db.reference(
                    "notification_tokens"
                )
                .child(patient_id)
                .delete()
            )

            return "Old token deleted"

        traceback.print_exc()

        return error


# ============================================================
# AISENSY APPOINTMENT
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

            "error":
                "Patient not found"

        }

    mobile = patient.get(
        "mobile"
    )

    recipient = format_whatsapp_number(
        mobile
    )

    if not recipient:

        return {

            "success": False,

            "error":
                "Invalid mobile number"

        }

    if not AISENSY_API_KEY:

        return {

            "success": False,

            "error":
                "AISENSY_API_KEY is missing"

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

            "success": False,

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

            "error":
                "Patient not found"

        }

    recipient = format_whatsapp_number(
        patient.get("mobile")
    )

    if not recipient:

        return {

            "success": False,

            "error":
                "Invalid mobile number"

        }

    if not AISENSY_API_KEY:

        return {

            "success": False,

            "error":
                "AISENSY_API_KEY is missing"

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
            "AISENSY FOLLOWUP:",
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
            "AISENSY FOLLOWUP ERROR:",
            str(e)
        )

        return {

            "success": False,

            "error":
                str(e)

        }


# ============================================================
# WHATSAPP / META WEBHOOK
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

    # --------------------------------------------------------
    # HEAD
    # --------------------------------------------------------

    if request.method == "HEAD":

        return "", 200

    # --------------------------------------------------------
    # GET VERIFICATION
    # --------------------------------------------------------

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

            hmac.compare_digest(
                token or "",
                WHATSAPP_VERIFY_TOKEN
            )

            and

            challenge

        ):

            print(
                "META WEBHOOK VERIFICATION SUCCESS"
            )

            return challenge, 200

        print(
            "META WEBHOOK VERIFICATION FAILED"
        )

        return (
            "Verification failed",
            403
        )

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    )

    print(
        "WHATSAPP WEBHOOK:",
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

        "service":
            "Statusly / MediQueue",

        "timestamp":
            utc_iso()

    })


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),

        debug=os.environ.get(
            "FLASK_DEBUG",
            "false"
        ).lower() == "true"

    )
