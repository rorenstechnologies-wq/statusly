from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_from_directory
)
import json
from flask_cors import CORS

import firebase_admin
from firebase_admin import (
    credentials,
    db,
    auth,
    messaging
)

from datetime import datetime, timedelta

import os
import requests
import traceback
import uuid

from dotenv import load_dotenv


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
# FIREBASE SERVICE WORKER
# ============================================================

@app.route("/firebase-messaging-sw.js")
def firebase_sw():

    print("SERVICE WORKER REQUESTED")

    return send_from_directory(
        "static",
        "firebase-messaging-sw.js"
    )


# ============================================================
# FIREBASE INITIALIZATION
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
    "AISENSY_API_KEY"
)

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
# FORMAT INDIAN WHATSAPP NUMBER
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
# TEMP DASHBOARD
#
# Cashfree returns here:
#
# /temp-dash?order_id=STATUSLY_xxxxx
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
# LOGIN API
# ============================================================

@app.route(
    "/login",
    methods=["POST"]
)
def login():

    try:

        token = request.headers.get(
            "Authorization"
        )

        if not token:

            return jsonify({
                "error": "No token"
            }), 401

        token = token.replace(
            "Bearer ",
            ""
        )

        decoded = auth.verify_id_token(
            token
        )

        uid = decoded["uid"]

        hospital = db.reference(
            f"hospitals/{uid}"
        ).get() or {}

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

        print(
            "LOGIN ERROR:",
            str(e)
        )

        traceback.print_exc()

        return jsonify({
            "error": str(e)
        }), 401


# ============================================================
# CASHFREE HELPERS
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
# ACTIVATE SUBSCRIPTION
# ============================================================

def activate_subscription(order_id):

    try:

        print(
            "========================================"
        )

        print(
            "ACTIVATE SUBSCRIPTION"
        )

        print(
            "Order ID:",
            order_id
        )

        print(
            "========================================"
        )


        payment_ref = db.reference(
            "payment_orders"
        ).child(
            order_id
        )

        payment_order = payment_ref.get()


        if not payment_order:

            return {
                "success": False,
                "error": "Local payment order not found"
            }


        # ----------------------------------------------------
        # PREVENT DUPLICATE ACTIVATION
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


        if not plan:

            return {
                "success": False,
                "error": "Plan missing"
            }


        # ----------------------------------------------------
        # EXPIRY
        # ----------------------------------------------------

        expiry = (
            datetime.utcnow()
            + timedelta(
                days=int(duration_days)
            )
        )


        # ----------------------------------------------------
        # GET CASHFREE PAYMENT
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
                "Cashfree Payments Response:",
                response.status_code,
                response.text
            )


            if response.ok:

                payments = (
                    response.json()
                    if isinstance(
                        response.json(),
                        list
                    )
                    else []
                )

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
                datetime.utcnow().isoformat()

        }


        db.reference(
            "subscriptions"
        ).child(
            uid
        ).set(
            subscription_data
        )


        # ----------------------------------------------------
        # MARK PAYMENT ORDER ACTIVATED
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
                datetime.utcnow().isoformat()

        })


        print(
            "SUBSCRIPTION ACTIVATED"
        )

        print(
            subscription_data
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

        print()
        print("=" * 60)
        print("CREATE PAYMENT ORDER")
        print("=" * 60)

        # ----------------------------------------------------
        # AUTHENTICATE FIREBASE USER
        # ----------------------------------------------------

        decoded = get_authenticated_user()

        if not decoded:

            return jsonify({

                "success": False,

                "error":
                    "Authentication required"

            }), 401

        # ----------------------------------------------------
        # UID FROM FIREBASE TOKEN
        # ----------------------------------------------------

        uid = decoded.get("uid")

        print(
            "AUTHENTICATED UID:",
            uid
        )

        if not uid:

            return jsonify({

                "success": False,

                "error":
                    "UID missing from Firebase token"

            }), 400

        # ----------------------------------------------------
        # REQUEST DATA
        # ----------------------------------------------------

        data = request.get_json(
            silent=True
        ) or {}

        plan = str(
            data.get(
                "plan",
                "basic"
            )
        ).lower()

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

        # ----------------------------------------------------
        # PLAN
        # ----------------------------------------------------

        if plan not in PLANS:

            return jsonify({

                "success": False,

                "error":
                    "Invalid plan"

            }), 400

        plan_data = PLANS[plan]

        amount = plan_data["amount"]

        duration_days = (
            plan_data["duration_days"]
        )

        # ----------------------------------------------------
        # CASHFREE CONFIG
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # PHONE
        # ----------------------------------------------------

        customer_phone = "".join(
            filter(
                str.isdigit,
                str(customer_phone)
            )
        )

        # For now, use a test/default phone if you don't
        # collect phone on the payment page.

        if len(customer_phone) == 0:

            customer_phone = "9999999999"

        if len(customer_phone) == 12:

            customer_phone = customer_phone[-10:]

        if len(customer_phone) != 10:

            return jsonify({

                "success": False,

                "error":
                    "Valid 10 digit customer phone is required"

            }), 400

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
    f"{STATUSLY_BASE_URL}/temp-dash"
    f"?order_id={order_id}"
)

        # ----------------------------------------------------
        # CASHFREE PAYLOAD
        # ----------------------------------------------------

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

        print(
            "ORDER ID:",
            order_id
        )

        print(
            "UID:",
            uid
        )

        print(
            "PLAN:",
            plan
        )

        print(
            "AMOUNT:",
            amount
        )

                # ----------------------------------------------------
        # CASHFREE
        # ----------------------------------------------------

        response = requests.post(
            f"{CASHFREE_BASE_URL}/orders",
            headers=cashfree_headers(),
            json=payload,
            timeout=30
        )

        print("CASHFREE STATUS:", response.status_code)
        print("CASHFREE RESPONSE:", response.text)

        if not response.ok:
            return jsonify({
                "success": False,
                "error": "Cashfree order creation failed",
                "cashfree_status": response.status_code,
                "cashfree_response": response.text
            }), response.status_code

        # ----------------------------------------------------
        # READ CASHFREE RESPONSE
        # ----------------------------------------------------

        result = response.json()

        payment_session_id = result.get(
            "payment_session_id"
        )

        print("========================================")
        print("CASHFREE CREATE ORDER RESPONSE")
        print(result)
        print("PAYMENT SESSION ID:")
        print(repr(payment_session_id))
        print("========================================")

        # ----------------------------------------------------
        # CHECK PAYMENT SESSION
        # ----------------------------------------------------

        if not payment_session_id:
            return jsonify({
                "success": False,
                "error": "payment_session_id missing",
                "cashfree_response": result
            }), 500

        # ----------------------------------------------------
        # SAVE PAYMENT ORDER
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
                datetime.utcnow().isoformat()

        })

        print("PAYMENT ORDER SAVED")
        print("=" * 60)

        # ----------------------------------------------------
        # RETURN TO FRONTEND
        # ----------------------------------------------------

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

            "success":
                False,

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

        print(
            "========================================"
        )

        print(
            "CHECKING CASHFREE ORDER"
        )

        print(
            "Order ID:",
            order_id
        )

        print(
            "========================================"
        )

        # ----------------------------------------------------
        # GET LOCAL ORDER
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # CHECK CASHFREE
        # ----------------------------------------------------

        response = requests.get(

            f"{CASHFREE_BASE_URL}/orders/"
            f"{order_id}",

            headers=cashfree_headers(),

            timeout=30

        )

        print(
            "CASHFREE ORDER STATUS CODE:",
            response.status_code
        )

        print(
            "CASHFREE ORDER RESPONSE:",
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

        # ----------------------------------------------------
        # CASHFREE ORDER DATA
        # ----------------------------------------------------

        cashfree_order = response.json()

        cashfree_status = cashfree_order.get(
            "order_status"
        )

        print(
            "CASHFREE ORDER STATUS:",
            cashfree_status
        )

        # ----------------------------------------------------
        # PAID
        # ----------------------------------------------------

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

            }), 200

        # ----------------------------------------------------
        # NOT PAID
        # ----------------------------------------------------

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

        }), 200

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
            "========================================"
        )

        print(
            "CASHFREE WEBHOOK"
        )

        print(
            data
        )

        print(
            "========================================"
        )


        # ----------------------------------------------------
        # Extract order ID
        # ----------------------------------------------------

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
        # DO NOT TRUST WEBHOOK ALONE
        #
        # We verify directly with Cashfree.
        # ----------------------------------------------------

        try:

            response = requests.get(

                f"{CASHFREE_BASE_URL}/orders/"
                f"{order_id}",

                headers=cashfree_headers(),

                timeout=30

            )


            print(
                "Webhook verification status:",
                response.status_code
            )

            print(
                "Webhook verification response:",
                response.text
            )


            if response.ok:

                order_data = (
                    response.json()
                )

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
# ============================================================
# CHECK SUBSCRIPTION
# ============================================================

@app.route(
    "/check-subscription",
    methods=["POST"]
)
def check_subscription():

    try:

        print()
        print("=" * 60)
        print("CHECK SUBSCRIPTION")
        print("=" * 60)

        # ----------------------------------------------------
        # GET FIREBASE USER FROM TOKEN
        # ----------------------------------------------------

        decoded = get_authenticated_user()

        if not decoded:

            print(
                "CHECK SUBSCRIPTION: AUTHENTICATION FAILED"
            )

            return jsonify({

                "success": False,

                "error":
                    "Authentication required"

            }), 401

        # ----------------------------------------------------
        # GET UID
        # ----------------------------------------------------

        uid = decoded.get("uid")

        print(
            "CHECK SUBSCRIPTION UID:",
            uid
        )

        if not uid:

            print(
                "CHECK SUBSCRIPTION: UID MISSING FROM TOKEN"
            )

            return jsonify({

                "success": False,

                "error":
                    "UID missing"

            }), 400

        # ----------------------------------------------------
        # GET SUBSCRIPTION
        # ----------------------------------------------------

        subscription = get_subscription(
            uid
        )

        print(
            "SUBSCRIPTION:",
            subscription
        )

        # ----------------------------------------------------
        # CHECK ACTIVE
        # ----------------------------------------------------

        active = subscription_is_active(
            uid
        )

        print(
            "ACTIVE:",
            active
        )

        print("=" * 60)

        return jsonify({

            "success":
                True,

            "uid":
                uid,

            "active":
                active,

            "subscription":
                subscription or {}

        }), 200

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
# GET AUTHENTICATED FIREBASE USER
# ============================================================

def get_authenticated_user():

    authorization = request.headers.get(
        "Authorization",
        ""
    )

    print(
        "AUTHORIZATION HEADER:",
        authorization[:30] + "..."
        if authorization
        else "MISSING"
    )

    # --------------------------------------------------------
    # CHECK HEADER
    # --------------------------------------------------------

    if not authorization:

        print(
            "AUTH ERROR: Authorization header missing"
        )

        return None


    # --------------------------------------------------------
    # CHECK BEARER
    # --------------------------------------------------------

    if not authorization.startswith("Bearer "):

        print(
            "AUTH ERROR: Invalid Authorization format"
        )

        return None


    # --------------------------------------------------------
    # GET TOKEN
    # --------------------------------------------------------

    token = authorization[7:].strip()


    if not token:

        print(
            "AUTH ERROR: Firebase token missing"
        )

        return None


    # --------------------------------------------------------
    # VERIFY FIREBASE TOKEN
    # --------------------------------------------------------

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
# GET SUBSCRIPTION
# ============================================================

def get_subscription(uid):

    if not uid:

        return None


    subscription = db.reference(
        "subscriptions"
    ).child(
        uid
    ).get()


    return subscription


# ============================================================
# CHECK WHETHER SUBSCRIPTION IS ACTIVE
# ============================================================

def subscription_is_active(uid):

    if not uid:

        return False


    subscription = get_subscription(
        uid
    )


    if not subscription:

        print(
            "NO SUBSCRIPTION FOUND FOR UID:",
            uid
        )

        return False


    # --------------------------------------------------------
    # PAYMENT STATUS
    # --------------------------------------------------------

    payment_status = subscription.get(
        "payment_status",
        ""
    )


    print(
        "PAYMENT STATUS:",
        payment_status
    )


    if payment_status != "PAID":

        print(
            "SUBSCRIPTION NOT PAID"
        )

        return False


    # --------------------------------------------------------
    # EXPIRY
    # --------------------------------------------------------

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


        if now < expiry:

            print(
                "SUBSCRIPTION ACTIVE"
            )

            return True


        print(
            "SUBSCRIPTION EXPIRED"
        )

        return False


    except Exception as e:

        print(
            "SUBSCRIPTION EXPIRY ERROR:",
            str(e)
        )

        return False
# ============================================================
# SAVE HOSPITAL
# ============================================================

@app.route(
    "/save_hospital",
    methods=["POST"]
)
def save_hospital():

    uid = request.form.get(
        "uid"
    )


    if not uid:

        return jsonify({
            "error": "UID missing"
        }), 400


    # --------------------------------------------------------
    # CHECK SUBSCRIPTION
    # --------------------------------------------------------

    subscription = db.reference(
        "subscriptions"
    ).child(
        uid
    ).get()


    if not subscription:

        return jsonify({

            "error":
                "Active subscription required"

        }), 403


    expiry_string = subscription.get(
        "expiry"
    )


    try:

        expiry = datetime.fromisoformat(
            expiry_string
        )

        if datetime.utcnow() >= expiry:

            return jsonify({

                "error":
                    "Subscription expired"

            }), 403

    except Exception:

        return jsonify({

            "error":
                "Invalid subscription"

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
            str(datetime.now()),

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

        "message":
            "Saved",

        "uid":
            uid

    })


# ============================================================
# HOSPITAL PAGE
# ============================================================

@app.route(
    "/hospital/<uid>"
)
def hospital_page(uid):

    data = db.reference(
        f"hospitals/{uid}"
    ).get()


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

    hospital = db.reference(
        f"hospitals/{uid}"
    ).get()


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


        print(
            "================================"
        )

        print(
            "BOOKING NEW APPOINTMENT"
        )

        print(
            "Hospital ID:",
            hospital_id
        )

        print(
            "FCM TOKEN:",
            fcm_token
        )

        print(
            "================================"
        )


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
                str(datetime.now())

        }


        # ----------------------------------------------------
        # SAVE APPOINTMENT
        # ----------------------------------------------------

        ref = db.reference(
            "appointments"
        ).push(
            appointment
        )


        patient_id = ref.key


        print(
            "NEW APPOINTMENT ID:",
            patient_id
        )


        # ----------------------------------------------------
        # SAVE FCM TOKEN
        # ----------------------------------------------------

        if fcm_token:

            db.reference(
                "notification_tokens"
            ).child(
                patient_id
            ).set({

                "token":
                    fcm_token

            })


            print(
                "TOKEN SAVED FOR:",
                patient_id
            )

        else:

            print(
                "NO FCM TOKEN RECEIVED"
            )


        # ----------------------------------------------------
        # AISENSY APPOINTMENT CONFIRMATION
        # ----------------------------------------------------

        whatsapp_result = (
            send_aisensy_appointment_confirmation(
                patient_id
            )
        )


        print(
            "Appointment WhatsApp Status:",
            whatsapp_result
        )

                     # ----------------------------------------------------
        # GET HOSPITAL DATA
        # ----------------------------------------------------

        hospital = db.reference(
            f"hospitals/{hospital_id}"
        ).get() or {}

        hospital_name = hospital.get(
            "hospital_name",
            "Hospital"
        )

        # ----------------------------------------------------
        # GET APPOINTMENT DATA
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # GET DOCTOR SPECIALIZATION
        # ----------------------------------------------------

        specialization = ""

        for doctor in hospital.get("doctors", []):

            if doctor.get("doctor_name") == doctor_name:

                specialization = doctor.get(
                    "specialization",
                    ""
                )

                break

        # ----------------------------------------------------
        # SHOW SUCCESS PAGE
        # ----------------------------------------------------

        return render_template(
            "success.html",

            patient_id=patient_id,

            hospital_name=hospital_name,

            doctor_name=doctor_name,

            specialization=specialization,

            appointment_date=appointment_date,

            appointment_time=appointment_time
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
    "/appointments/<uid>"
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

    data = db.reference(
        "appointments"
    ).get() or {}


    patients = []


    for key, patient in data.items():

        if patient.get(
            "hospital_id"
        ) != uid:

            continue


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

                "error":
                    "Patient ID missing"

            }), 400


        # ----------------------------------------------------
        # CHECK PATIENT
        # ----------------------------------------------------

        patient = db.reference(
            "appointments"
        ).child(
            patient_id
        ).get()


        if not patient:

            return jsonify({

                "error":
                    "Patient not found"

            }), 404


        # ----------------------------------------------------
        # SAVE FOLLOW-UP
        # ----------------------------------------------------

        db.reference(
            "appointments/" + patient_id
        ).update({

            "next_visit_date":
                next_visit_date,

            "doctor_notes":
                doctor_notes,

            "followup_created_at":
                str(datetime.now())

        })


        # ----------------------------------------------------
        # FCM
        # ----------------------------------------------------

        fcm_result = send_notification(
            patient_id
        )


        print(
            "FCM Notification Status:",
            fcm_result
        )


        # ----------------------------------------------------
        # AISENSY FOLLOW-UP
        # ----------------------------------------------------

        whatsapp_result = (
            send_whatsapp_followup(
                patient_id
            )
        )


        print(
            "WhatsApp Status:",
            whatsapp_result
        )


        # ----------------------------------------------------
        # RESPONSE
        # ----------------------------------------------------

        return jsonify({

            "message":
                "Follow-up Saved",

            "notification":
                fcm_result,

            "whatsapp":
                whatsapp_result

        }), 200


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

        data = request.json or {}


        token = data.get(
            "token"
        )

        patient_id = data.get(
            "patient_id"
        )


        if not token or not patient_id:

            return jsonify({

                "error":
                    "Token or Patient ID missing"

            }), 400


        db.reference(
            "notification_tokens/" + patient_id
        ).set({

            "token":
                token

        })


        return jsonify({

            "message":
                "Token saved"

        })


    except Exception as e:

        print(
            "SAVE TOKEN ERROR:",
            str(e)
        )


        return jsonify({

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


        print(
            "Patient:",
            patient
        )

        print(
            "Token Data:",
            token_data
        )


        if not token_data:

            return "No token found"


        token = token_data.get(
            "token"
        )


        if not token:

            return "Token missing"


        if not patient:

            return "Patient not found"


        patient_name = patient.get(
            "patient_name",
            "Patient"
        )


        visit_date = patient.get(
            "next_visit_date",
            ""
        )


        message = messaging.Message(

            token=token,

            notification=
                messaging.Notification(

                    title=
                        "Hospital Reminder",

                    body=
                        f"{patient_name}, "
                        f"your next visit is on "
                        f"{visit_date}"

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
                                f"{patient_name}, "
                                f"your next visit is on "
                                f"{visit_date}",

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

    print(
        "========================================"
    )

    print(
        "AISENSY APPOINTMENT CONFIRMATION"
    )

    print(
        "Patient ID:",
        patient_id
    )

    print(
        "========================================"
    )


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


    try:

        response = requests.post(

            AISENSY_API_URL,

            json=payload,

            timeout=30

        )


        print(
            "AISENSY APPOINTMENT STATUS:",
            response.status_code
        )

        print(
            "AISENSY RESPONSE:",
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
# AISENSY FOLLOW-UP WHATSAPP
# ============================================================

def send_whatsapp_followup(patient_id):

    print(
        "========================================"
    )

    print(
        "AISENSY FOLLOW-UP WHATSAPP"
    )

    print(
        "Patient ID:",
        patient_id
    )

    print(
        "========================================"
    )


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


    try:

        response = requests.post(

            AISENSY_API_URL,

            json=payload,

            timeout=30

        )


        print(
            "AISENSY FOLLOW-UP STATUS:",
            response.status_code
        )

        print(
            "AISENSY FOLLOW-UP RESPONSE:",
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

    # --------------------------------------------------------
    # HEAD
    # --------------------------------------------------------

    if request.method == "HEAD":

        return "", 200


    # --------------------------------------------------------
    # GET - META VERIFICATION
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


        print(
            "========== META WEBHOOK VERIFICATION =========="
        )

        print(
            "Mode:",
            repr(mode)
        )

        print(
            "Token:",
            repr(token)
        )

        print(
            "Challenge:",
            repr(challenge)
        )


        if (

            mode == "subscribe"

            and

            token ==
            "mediqueue_webhook_2026"

            and

            challenge

        ):

            print(
                "META VERIFICATION SUCCESS"
            )

            return challenge, 200


        print(
            "META VERIFICATION FAILED"
        )


        return (
            "Verification failed",
            403
        )


    # --------------------------------------------------------
    # POST - WHATSAPP EVENTS
    # --------------------------------------------------------

    if request.method == "POST":

        data = request.get_json(
            silent=True
        )


        print(
            "========== WHATSAPP WEBHOOK EVENT =========="
        )

        print(
            data
        )

        print(
            "============================================"
        )


        return (
            "EVENT_RECEIVED",
            200
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )
