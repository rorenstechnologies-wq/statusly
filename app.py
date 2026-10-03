import os
import json
import hmac
import hashlib
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
)
from flask_cors import CORS

import firebase_admin
from firebase_admin import (
    credentials,
    db,
    auth,
    messaging,
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

app = Flask(__name__)
CORS(app)

app.config["JSON_SORT_KEYS"] = False


# ============================================================
# BASIC CONFIG
# ============================================================

BASE_URL = os.getenv(
    "BASE_URL",
    "https://statusly.in"
).rstrip("/")

FIREBASE_DATABASE_URL = os.getenv(
    "FIREBASE_DATABASE_URL",
    "https://hospital-57fc8-default-rtdb.firebaseio.com"
)

FIREBASE_SERVICE_ACCOUNT = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT"
)

AISENSY_API_KEY = os.getenv(
    "AISENSY_API_KEY",
    ""
)

AISENSY_URL = os.getenv(
    "AISENSY_URL",
    "https://backend.aisensy.com/campaign/t1/api/v2"
)

CASHFREE_CLIENT_ID = os.getenv(
    "CASHFREE_CLIENT_ID",
    ""
)

CASHFREE_CLIENT_SECRET = os.getenv(
    "CASHFREE_CLIENT_SECRET",
    ""
)

CASHFREE_BASE_URL = os.getenv(
    "CASHFREE_BASE_URL",
    "https://sandbox.cashfree.com/pg"
).rstrip("/")

CASHFREE_API_VERSION = os.getenv(
    "CASHFREE_API_VERSION",
    "2025-01-01"
)

CASHFREE_WEBHOOK_SECRET = os.getenv(
    "CASHFREE_WEBHOOK_SECRET",
    ""
)


# ============================================================
# FIREBASE INITIALIZATION
# ============================================================

if not firebase_admin._apps:

    if FIREBASE_SERVICE_ACCOUNT:
        try:
            service_account_info = json.loads(
                FIREBASE_SERVICE_ACCOUNT
            )

            cred = credentials.Certificate(
                service_account_info
            )

            firebase_admin.initialize_app(
                cred,
                {
                    "databaseURL": FIREBASE_DATABASE_URL
                }
            )

        except Exception as e:
            print("Firebase initialization error:", e)
            raise

    else:
        # Local development fallback.
        # Make sure GOOGLE_APPLICATION_CREDENTIALS is configured.
        try:
            cred = credentials.ApplicationDefault()

            firebase_admin.initialize_app(
                cred,
                {
                    "databaseURL": FIREBASE_DATABASE_URL
                }
            )

        except Exception as e:
            print("Firebase initialization error:", e)
            raise


# ============================================================
# COMMON HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def utc_now_iso():
    return utc_now().isoformat()


def normalize_mobile(mobile):
    """
    Convert Indian mobile numbers to last 10 digits.

    Examples:
    9876543210
    +919876543210
    919876543210
    -> 9876543210
    """

    digits = "".join(
        filter(
            str.isdigit,
            str(mobile or "")
        )
    )

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[-10:]

    return digits


def format_whatsapp_number(mobile):
    """
    AiSensy generally expects country code.
    """

    mobile = normalize_mobile(mobile)

    if len(mobile) == 10:
        return "91" + mobile

    return mobile


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return default


def safe_float(value, default=0):
    try:
        return float(value)
    except Exception:
        return default


def parse_date(value):
    if not value:
        return None

    value = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                value,
                fmt
            )
        except Exception:
            pass

    return None


def appointment_sort_key(appointment):
    """
    Latest appointment first.

    Date + time are combined so same-day appointments
    are also sorted correctly.
    """

    date_value = appointment.get(
        "appointment_date",
        ""
    )

    time_value = appointment.get(
        "appointment_time",
        ""
    )

    dt = parse_date(date_value)

    if not dt:
        dt = datetime.min

    # Extract HH:MM where possible.
    time_text = str(
        time_value or "00:00"
    )

    try:
        parts = time_text.split(":")
        hour = safe_int(parts[0], 0)
        minute = safe_int(
            parts[1],
            0
        ) if len(parts) > 1 else 0

        dt = dt.replace(
            hour=hour,
            minute=minute
        )

    except Exception:
        pass

    return dt


def get_appointment_day_status(date_value):
    """
    Returns:
    TODAY
    UPCOMING
    PAST
    """

    dt = parse_date(date_value)

    if not dt:
        return "UNKNOWN"

    today = datetime.now().date()

    if dt.date() == today:
        return "TODAY"

    if dt.date() > today:
        return "UPCOMING"

    return "PAST"


# ============================================================
# AUTH HELPERS
# ============================================================

def get_bearer_token():
    header = request.headers.get(
        "Authorization",
        ""
    )

    if not header:
        return None

    if header.lower().startswith("bearer "):
        return header[7:].strip()

    return None


def verify_firebase_token():
    token = get_bearer_token()

    if not token:
        raise ValueError(
            "Authorization token missing"
        )

    decoded = auth.verify_id_token(
        token
    )

    return decoded


def authenticated_uid():
    decoded = verify_firebase_token()
    return decoded.get("uid")


def require_hospital_access(hospital_id):
    decoded = verify_firebase_token()

    uid = decoded.get("uid")

    if uid != hospital_id:
        raise PermissionError(
            "Unauthorized hospital access"
        )

    return decoded


# ============================================================
# SUBSCRIPTION HELPERS
# ============================================================

def get_subscription(uid):
    if not uid:
        return {}

    try:
        data = db.reference(
            f"subscriptions/{uid}"
        ).get()

        return data or {}

    except Exception as e:
        print("Subscription read error:", e)
        return {}


def is_subscription_active(uid):
    subscription = get_subscription(uid)

    if not subscription:
        return False

    payment_status = str(
        subscription.get(
            "payment_status",
            ""
        )
    ).upper()

    if payment_status != "PAID":
        return False

    expiry = subscription.get(
        "expiry"
    )

    if not expiry:
        return False

    try:
        expiry_dt = datetime.fromisoformat(
            str(expiry).replace(
                "Z",
                "+00:00"
            )
        )

        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(
                tzinfo=timezone.utc
            )

        return expiry_dt > utc_now()

    except Exception:
        return False


def subscription_response(uid):
    subscription = get_subscription(uid)

    active = is_subscription_active(uid)

    return {
        "active": active,
        "subscription": subscription
    }


# ============================================================
# PATIENT PRICING
# ============================================================

DEFAULT_NEW_PATIENT_CHARGE = 500
DEFAULT_OLD_PATIENT_CHARGE = 300


def get_patient_pricing(hospital_id):
    try:
        data = db.reference(
            f"hospital_settings/{hospital_id}/patient_pricing"
        ).get() or {}

        return {
            "new_patient_charge": safe_float(
                data.get(
                    "new_patient_charge",
                    DEFAULT_NEW_PATIENT_CHARGE
                ),
                DEFAULT_NEW_PATIENT_CHARGE
            ),
            "old_patient_charge": safe_float(
                data.get(
                    "old_patient_charge",
                    DEFAULT_OLD_PATIENT_CHARGE
                ),
                DEFAULT_OLD_PATIENT_CHARGE
            )
        }

    except Exception as e:
        print("Pricing read error:", e)

        return {
            "new_patient_charge":
                DEFAULT_NEW_PATIENT_CHARGE,
            "old_patient_charge":
                DEFAULT_OLD_PATIENT_CHARGE
        }


# ============================================================
# PATIENT REGISTRATION / VISIT
# ============================================================

def register_patient_visit(
    hospital_id,
    patient_name,
    mobile
):
    """
    Creates or updates hospital-scoped patient.

    IMPORTANT:
    - First visit = NEW
    - Existing patient keeps NEW/OLD status
    - Visit count increases automatically
    - Charge is calculated NOW and returned to appointment
    - Appointment stores historical charge
    """

    mobile_key = normalize_mobile(mobile)

    if not mobile_key:
        raise ValueError(
            "Valid mobile number is required"
        )

    patient_ref = db.reference(
        f"patients/{hospital_id}/{mobile_key}"
    )

    patient = patient_ref.get()

    pricing = get_patient_pricing(
        hospital_id
    )

    if not patient:
        patient_status = "NEW"
        visit_number = 1

        patient = {
            "hospital_id": hospital_id,
            "mobile": mobile_key,
            "patient_name": patient_name or "",
            "patient_status": "NEW",
            "visit_count": 1,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso()
        }

    else:
        existing_status = str(
            patient.get(
                "patient_status",
                "NEW"
            )
        ).upper()

        if existing_status not in [
            "NEW",
            "OLD"
        ]:
            existing_status = "NEW"

        patient_status = existing_status

        previous_visit_count = safe_int(
            patient.get(
                "visit_count",
                0
            ),
            0
        )

        visit_number = (
            previous_visit_count + 1
        )

        patient["hospital_id"] = hospital_id
        patient["mobile"] = mobile_key

        if patient_name:
            patient["patient_name"] = (
                patient_name
            )

        patient["patient_status"] = (
            patient_status
        )

        patient["visit_count"] = (
            visit_number
        )

        patient["updated_at"] = (
            utc_now_iso()
        )

    if patient_status == "OLD":
        charge = pricing[
            "old_patient_charge"
        ]
    else:
        charge = pricing[
            "new_patient_charge"
        ]

    patient_ref.set(patient)

    return {
        "patient_key": mobile_key,
        "patient_status": patient_status,
        "visit_number": visit_number,
        "charge": charge
    }


# ============================================================
# PATIENT MASTER DATA
# ============================================================

def get_patient_master(
    hospital_id,
    mobile
):
    mobile_key = normalize_mobile(
        mobile
    )

    if not mobile_key:
        return None

    try:
        return db.reference(
            f"patients/{hospital_id}/{mobile_key}"
        ).get()

    except Exception:
        return None


# ============================================================
# DOCTOR MAKES PATIENT OLD
# ============================================================

@app.route(
    "/api/doctor/make-patient-old",
    methods=["POST"]
)
def make_patient_old():

    try:
        decoded = verify_firebase_token()

        hospital_id = decoded.get("uid")

        data = request.get_json(
            silent=True
        ) or {}

        mobile = normalize_mobile(
            data.get("mobile")
        )

        if not mobile:
            return jsonify({
                "success": False,
                "message":
                    "Mobile number required"
            }), 400

        patient_ref = db.reference(
            f"patients/{hospital_id}/{mobile}"
        )

        patient = patient_ref.get()

        if not patient:
            return jsonify({
                "success": False,
                "message":
                    "Patient not found"
            }), 404

        patient["patient_status"] = "OLD"
        patient["updated_at"] = (
            utc_now_iso()
        )

        patient_ref.set(patient)

        # ----------------------------------------------------
        # Update appointment TYPE only.
        #
        # DO NOT change historical charge.
        # ----------------------------------------------------

        appointments_ref = db.reference(
            "appointments"
        )

        all_appointments = (
            appointments_ref.get() or {}
        )

        changed = 0

        for appointment_id, appointment in (
            all_appointments.items()
        ):

            if not isinstance(
                appointment,
                dict
            ):
                continue

            if appointment.get(
                "hospital_id"
            ) != hospital_id:
                continue

            appointment_mobile = normalize_mobile(
                appointment.get("mobile")
            )

            if appointment_mobile != mobile:
                continue

            appointment[
                "patient_status"
            ] = "OLD"

            # Historical charge intentionally preserved.
            appointments_ref.child(
                appointment_id
            ).update({
                "patient_status": "OLD"
            })

            changed += 1

        return jsonify({
            "success": True,
            "message":
                "Patient marked as OLD",
            "patient_status": "OLD",
            "appointments_updated":
                changed
        })

    except PermissionError as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 403

    except Exception as e:

        print(
            "make_patient_old error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================================
# ADMIN PATIENT SETTINGS
# ============================================================

@app.route(
    "/api/admin/patient-settings/<hospital_id>",
    methods=["GET", "POST"]
)
def patient_settings(hospital_id):

    try:

        require_hospital_access(
            hospital_id
        )

        ref = db.reference(
            f"hospital_settings/{hospital_id}/patient_pricing"
        )

        if request.method == "GET":

            pricing = get_patient_pricing(
                hospital_id
            )

            return jsonify({
                "success": True,
                "pricing": pricing
            })

        data = request.get_json(
            silent=True
        ) or {}

        new_charge = safe_float(
            data.get(
                "new_patient_charge"
            ),
            DEFAULT_NEW_PATIENT_CHARGE
        )

        old_charge = safe_float(
            data.get(
                "old_patient_charge"
            ),
            DEFAULT_OLD_PATIENT_CHARGE
        )

        if new_charge < 0:
            return jsonify({
                "success": False,
                "message":
                    "NEW patient charge cannot be negative"
            }), 400

        if old_charge < 0:
            return jsonify({
                "success": False,
                "message":
                    "OLD patient charge cannot be negative"
            }), 400

        ref.set({
            "new_patient_charge":
                new_charge,
            "old_patient_charge":
                old_charge,
            "updated_at":
                utc_now_iso()
        })

        return jsonify({
            "success": True,
            "message":
                "Patient pricing updated",
            "pricing": {
                "new_patient_charge":
                    new_charge,
                "old_patient_charge":
                    old_charge
            }
        })

    except Exception as e:

        print(
            "patient settings error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    return render_template(
        "index.html"
    )


@app.route("/login-page")
def login_page():
    return render_template(
        "login.html"
    )


@app.route("/payment")
def payment_page():
    return render_template(
        "payment.html"
    )


@app.route("/dashboard")
def dashboard():
    return render_template(
        "dashboard.html"
    )


@app.route("/temp-dash")
def temp_dash():
    return render_template(
        "temp-dash.html"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["POST"]
)
def login():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        id_token = data.get(
            "idToken"
        )

        if not id_token:
            return jsonify({
                "success": False,
                "message":
                    "Firebase ID token required"
            }), 400

        decoded = auth.verify_id_token(
            id_token
        )

        uid = decoded.get(
            "uid"
        )

        hospital = db.reference(
            f"hospitals/{uid}"
        ).get() or {}

        subscription = get_subscription(
            uid
        )

        active = is_subscription_active(
            uid
        )

        return jsonify({
            "success": True,
            "uid": uid,
            "hospitalId": uid,
            "hospitalName":
                hospital.get(
                    "hospital_name",
                    hospital.get(
                        "name",
                        ""
                    )
                ),
            "hospital": hospital,
            "subscription":
                subscription,
            "subscription_active":
                active
        })

    except Exception as e:

        print(
            "Login error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 401


# ============================================================
# CHECK SUBSCRIPTION
# ============================================================

@app.route(
    "/check-subscription",
    methods=["POST"]
)
def check_subscription():

    try:

        decoded = verify_firebase_token()

        uid = decoded.get(
            "uid"
        )

        return jsonify(
            subscription_response(
                uid
            )
        )

    except Exception as e:

        return jsonify({
            "active": False,
            "message": str(e)
        }), 401


# ============================================================
# CASHFREE HELPERS
# ============================================================

def cashfree_headers():

    return {
        "Content-Type":
            "application/json",
        "x-client-id":
            CASHFREE_CLIENT_ID,
        "x-client-secret":
            CASHFREE_CLIENT_SECRET,
        "x-api-version":
            CASHFREE_API_VERSION,
        "x-request-id":
            hashlib.sha256(
                os.urandom(32)
            ).hexdigest()
    }


# ============================================================
# CASHFREE CREATE ORDER
# ============================================================

@app.route(
    "/create-payment-order",
    methods=["POST"]
)
def create_payment_order():

    try:

        decoded = verify_firebase_token()

        uid = decoded.get(
            "uid"
        )

        data = request.get_json(
            silent=True
        ) or {}

        plan = str(
            data.get(
                "plan",
                "basic"
            )
        ).lower()

        plans = {

            "basic": {
                "amount": 1,
                "days": 30
            },

            "standard": {
                "amount": 1000,
                "days": 180
            },

            "premium": {
                "amount": 2000,
                "days": 365
            }
        }

        if plan not in plans:
            return jsonify({
                "success": False,
                "message":
                    "Invalid plan"
            }), 400

        plan_info = plans[plan]

        order_id = (
            "STATUSLY_"
            + datetime.now(
                timezone.utc
            ).strftime(
                "%Y%m%d%H%M%S"
            )
            + "_"
            + hashlib.sha1(
                os.urandom(16)
            ).hexdigest()[:8]
        )

        hospital = db.reference(
            f"hospitals/{uid}"
        ).get() or {}

        customer_phone = normalize_mobile(
            data.get(
                "phone",
                hospital.get(
                    "phone",
                    ""
                )
            )
        )

        customer_email = data.get(
            "email",
            hospital.get(
                "email",
                f"{uid}@statusly.in"
            )
        )

        payload = {

            "order_id":
                order_id,

            "order_amount":
                plan_info["amount"],

            "order_currency":
                "INR",

            "customer_details": {

                "customer_id":
                    uid,

                "customer_name":
                    hospital.get(
                        "hospital_name",
                        "Statusly Hospital"
                    ),

                "customer_email":
                    customer_email,

                "customer_phone":
                    customer_phone or "9999999999"
            },

            "order_meta": {

                "return_url":
                    f"{BASE_URL}/temp-dash?order_id={order_id}",

                "notify_url":
                    f"{BASE_URL}/cashfree/webhook"
            },

            "order_note":
                f"Statusly {plan} subscription"
        }

        response = requests.post(
            f"{CASHFREE_BASE_URL}/orders",
            headers=cashfree_headers(),
            json=payload,
            timeout=30
        )

        result = response.json()

        if response.status_code >= 400:

            print(
                "Cashfree order error:",
                result
            )

            return jsonify({
                "success": False,
                "message":
                    result.get(
                        "message",
                        "Cashfree order creation failed"
                    ),
                "cashfree":
                    result
            }), response.status_code

        db.reference(
            f"payment_orders/{uid}/{order_id}"
        ).set({

            "order_id":
                order_id,

            "plan":
                plan,

            "amount":
                plan_info["amount"],

            "days":
                plan_info["days"],

            "status":
                "CREATED",

            "created_at":
                utc_now_iso()
        })

        return jsonify({
            "success": True,
            "order_id":
                order_id,
            "payment_session_id":
                result.get(
                    "payment_session_id"
                ),
            "order":
                result
        })

    except Exception as e:

        print(
            "create payment error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
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

        decoded = verify_firebase_token()

        uid = decoded.get(
            "uid"
        )

        response = requests.get(
            f"{CASHFREE_BASE_URL}/orders/{order_id}",
            headers=cashfree_headers(),
            timeout=30
        )

        result = response.json()

        return jsonify({
            "success":
                response.status_code < 400,
            "order":
                result
        }), response.status_code

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================================
# ACTIVATE SUBSCRIPTION
# ============================================================

def activate_subscription_from_order(
    order_id,
    order_data=None
):

    payment_order = None
    uid = None

    # --------------------------------------------------------
    # Find order owner
    # --------------------------------------------------------

    orders_root = db.reference(
        "payment_orders"
    ).get() or {}

    for possible_uid, orders in (
        orders_root.items()
    ):

        if not isinstance(
            orders,
            dict
        ):
            continue

        if order_id in orders:

            uid = possible_uid

            payment_order = orders[
                order_id
            ]

            break

    if not uid:
        return False, "Order owner not found"

    # --------------------------------------------------------
    # Verify order from Cashfree
    # --------------------------------------------------------

    try:

        response = requests.get(
            f"{CASHFREE_BASE_URL}/orders/{order_id}",
            headers=cashfree_headers(),
            timeout=30
        )

        cashfree_order = response.json()

        if response.status_code >= 400:
            return False, (
                "Unable to verify Cashfree order"
            )

    except Exception as e:

        return False, str(e)

    order_status = str(
        cashfree_order.get(
            "order_status",
            ""
        )
    ).upper()

    if order_status != "PAID":

        return False, (
            f"Order not paid: {order_status}"
        )

    # --------------------------------------------------------
    # Prevent duplicate activation
    # --------------------------------------------------------

    subscription_ref = db.reference(
        f"subscriptions/{uid}"
    )

    current = subscription_ref.get() or {}

    if current.get(
        "activated_order_id"
    ) == order_id:

        return True, "Already activated"

    # --------------------------------------------------------
    # Plan information
    # --------------------------------------------------------

    plan = str(
        (payment_order or {}).get(
            "plan",
            "basic"
        )
    ).lower()

    days = safe_int(
        (payment_order or {}).get(
            "days",
            30
        ),
        30
    )

    amount = safe_float(
        (payment_order or {}).get(
            "amount",
            cashfree_order.get(
                "order_amount",
                0
            )
        )
    )

    now = utc_now()

    current_expiry = None

    existing_expiry = current.get(
        "expiry"
    )

    if existing_expiry:

        try:

            current_expiry = datetime.fromisoformat(
                str(
                    existing_expiry
                ).replace(
                    "Z",
                    "+00:00"
                )
            )

            if current_expiry.tzinfo is None:
                current_expiry = (
                    current_expiry.replace(
                        tzinfo=timezone.utc
                    )
                )

        except Exception:
            current_expiry = None

    if current_expiry and current_expiry > now:
        start = current_expiry
    else:
        start = now

    expiry = start + timedelta(
        days=days
    )

    subscription_ref.set({

        "payment_status":
            "PAID",

        "plan":
            plan,

        "amount":
            amount,

        "days":
            days,

        "activated_order_id":
            order_id,

        "activated_at":
            now.isoformat(),

        "start":
            start.isoformat(),

        "expiry":
            expiry.isoformat()
    })

    db.reference(
        f"payment_orders/{uid}/{order_id}"
    ).update({

        "status":
            "PAID",

        "activated_at":
            now.isoformat()
    })

    return True, "Subscription activated"


# ============================================================
# CASHFREE WEBHOOK
# ============================================================

@app.route(
    "/cashfree/webhook",
    methods=["POST"]
)
@app.route(
    "/webhook",
    methods=["POST"]
)
def cashfree_webhook():

    try:

        payload = request.get_json(
            silent=True
        ) or {}

        order_data = payload.get(
            "data",
            {}
        )

        order = order_data.get(
            "order",
            {}
        )

        order_id = order.get(
            "order_id"
        )

        payment = order_data.get(
            "payment",
            {}
        )

        payment_status = str(
            payment.get(
                "payment_status",
                order.get(
                    "order_status",
                    ""
                )
            )
        ).upper()

        if not order_id:
            return jsonify({
                "success": False,
                "message":
                    "order_id missing"
            }), 400

        if payment_status in [
            "SUCCESS",
            "PAID",
            "SUCCESSFUL"
        ]:

            success, message = (
                activate_subscription_from_order(
                    order_id,
                    payload
                )
            )

            if not success:

                return jsonify({
                    "success": False,
                    "message":
                        message
                }), 400

            return jsonify({
                "success": True,
                "message":
                    message
            })

        return jsonify({
            "success": True,
            "message":
                f"Payment status: {payment_status}"
        })

    except Exception as e:

        print(
            "Cashfree webhook error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
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

        decoded = verify_firebase_token()

        uid = decoded.get(
            "uid"
        )

        if not is_subscription_active(
            uid
        ):
            return jsonify({
                "success": False,
                "message":
                    "Active subscription required"
            }), 403

        data = request.get_json(
            silent=True
        ) or {}

        existing = db.reference(
            f"hospitals/{uid}"
        ).get() or {}

        hospital = dict(
            existing
        )

        # ----------------------------------------------------
        # Preserve all existing fields.
        # ----------------------------------------------------

        for key, value in data.items():

            if key == "uid":
                continue

            hospital[key] = value

        hospital[
            "uid"
        ] = uid

        hospital.setdefault(
            "hospital_name",
            data.get(
                "hospital_name",
                ""
            )
        )

        hospital[
            "updated_at"
        ] = utc_now_iso()

        hospital.setdefault(
            "created_at",
            utc_now_iso()
        )

        db.reference(
            f"hospitals/{uid}"
        ).set(hospital)

        return jsonify({
            "success": True,
            "message":
                "Hospital saved successfully",
            "hospital":
                hospital
        })

    except Exception as e:

        print(
            "save hospital error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================================
# PUBLIC HOSPITAL PAGE
# ============================================================

@app.route(
    "/hospital/<hospital_id>"
)
def hospital_page(hospital_id):

    hospital = db.reference(
        f"hospitals/{hospital_id}"
    ).get()

    if not hospital:
        return (
            "Hospital not found",
            404
        )

    return render_template(
        "hospital.html",
        hospital=hospital,
        hospital_id=hospital_id
    )


# ============================================================
# PUBLIC BOOKING PAGE
# ============================================================

@app.route(
    "/hospital/<hospital_id>/book"
)
def hospital_booking_page(
    hospital_id
):

    hospital = db.reference(
        f"hospitals/{hospital_id}"
    ).get()

    if not hospital:
        return (
            "Hospital not found",
            404
        )

    return render_template(
        "appointment.html",
        hospital=hospital,
        hospital_id=hospital_id
    )


# ============================================================
# VOICE BOOKING PAGE
# ============================================================

@app.route(
    "/voice/<hospital_id>"
)
def voice_booking_page(
    hospital_id
):

    hospital = db.reference(
        f"hospitals/{hospital_id}"
    ).get()

    if not hospital:
        return (
            "Hospital not found",
            404
        )

    return render_template(
        "voice-booking.html",
        hospital=hospital,
        hospital_id=hospital_id
    )


# ============================================================
# VOICE BOOKING HOSPITAL API
# ============================================================

@app.route(
    "/api/voice/hospital/<hospital_id>",
    methods=["GET"]
)
def voice_hospital_data(
    hospital_id
):

    hospital = db.reference(
        f"hospitals/{hospital_id}"
    ).get()

    if not hospital:

        return jsonify({
            "success": False,
            "message":
                "Hospital not found"
        }), 404

    return jsonify({
        "success": True,
        "hospital": hospital,
        "hospital_id":
            hospital_id
    })


# ============================================================
# BOOK APPOINTMENT - COMMON FUNCTION
# ============================================================

def create_appointment(
    hospital_id,
    data,
    booking_source="WEB"
):

    if not hospital_id:
        raise ValueError(
            "Hospital ID required"
        )

    hospital = db.reference(
        f"hospitals/{hospital_id}"
    ).get()

    if not hospital:
        raise ValueError(
            "Hospital not found"
        )

    patient_name = str(
        data.get(
            "patient_name",
            ""
        )
    ).strip()

    mobile = normalize_mobile(
        data.get(
            "mobile"
        )
    )

    if not patient_name:
        raise ValueError(
            "Patient name required"
        )

    if len(mobile) != 10:
        raise ValueError(
            "Valid 10 digit mobile required"
        )

    appointment_date = str(
        data.get(
            "appointment_date",
            ""
        )
    ).strip()

    if not appointment_date:
        raise ValueError(
            "Appointment date required"
        )

    appointment_time = str(
        data.get(
            "appointment_time",
            ""
        )
    ).strip()

    doctor_name = str(
        data.get(
            "doctor_name",
            ""
        )
    ).strip()

    specialization = str(
        data.get(
            "specialization",
            ""
        )
    ).strip()

    # --------------------------------------------------------
    # PATIENT MASTER
    # --------------------------------------------------------

    patient_info = register_patient_visit(
        hospital_id=(
            hospital_id
        ),
        patient_name=(
            patient_name
        ),
        mobile=mobile
    )

    patient_status = patient_info[
        "patient_status"
    ]

    visit_number = patient_info[
        "visit_number"
    ]

    charge = patient_info[
        "charge"
    ]

    # --------------------------------------------------------
    # PATIENT NUMBER
    #
    # Current counter is kept compatible with existing system.
    # --------------------------------------------------------

    counter_ref = db.reference(
        "counters/patient_no"
    )

    counter_data = (
        counter_ref.get()
        or 0
    )

    patient_no = (
        safe_int(
            counter_data,
            0
        ) + 1
    )

    counter_ref.set(
        patient_no
    )

    # --------------------------------------------------------
    # APPOINTMENT
    # --------------------------------------------------------

    appointment = {

        "hospital_id":
            hospital_id,

        "patient_no":
            patient_no,

        "patient_key":
            patient_info[
                "patient_key"
            ],

        "patient_name":
            patient_name,

        "doctor_name":
            doctor_name,

        "specialization":
            specialization,

        "gender":
            data.get(
                "gender",
                ""
            ),

        "age":
            data.get(
                "age",
                ""
            ),

        "mobile":
            mobile,

        "address":
            data.get(
                "address",
                ""
            ),

        "appointment_date":
            appointment_date,

        "appointment_time":
            appointment_time,

        # ----------------------------------------------------
        # IMPORTANT
        # These are SNAPSHOT values.
        # Future pricing changes must NOT modify them.
        # ----------------------------------------------------

        "visit_number":
            visit_number,

        "patient_status":
            patient_status,

        "charge":
            charge,

        "booking_source":
            booking_source,

        "created_at":
            utc_now_iso(),

        "updated_at":
            utc_now_iso(),

        "patient_visit":
            visit_number
    }

    ref = db.reference(
        "appointments"
    ).push(
        appointment
    )

    appointment_id = ref.key

    appointment[
        "id"
    ] = appointment_id

    return appointment


# ============================================================
# NORMAL BOOKING
# ============================================================

@app.route(
    "/book_appointment",
    methods=["POST"]
)
def book_appointment():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        hospital_id = data.get(
            "hospital_id"
        )

        appointment = create_appointment(
            hospital_id=(
                hospital_id
            ),
            data=data,
            booking_source="WEB"
        )

        # ----------------------------------------------------
        # Send WhatsApp confirmation
        # ----------------------------------------------------

        try:
            send_appointment_whatsapp(
                appointment
            )
        except Exception as e:
            print(
                "WhatsApp confirmation error:",
                e
            )

        # ----------------------------------------------------
        # Send dashboard notification
        # ----------------------------------------------------

        try:
            send_fcm_to_hospital(
                hospital_id,
                appointment
            )
        except Exception as e:
            print(
                "FCM error:",
                e
            )

        return jsonify({
            "success": True,
            "message":
                "Appointment booked successfully",
            "appointment":
                appointment
        })

    except Exception as e:

        print(
            "book appointment error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


# ============================================================
# VOICE BOOKING API
# ============================================================

@app.route(
    "/api/voice/book",
    methods=["POST"]
)
def voice_book():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        hospital_id = data.get(
            "hospital_id"
        )

        appointment = create_appointment(
            hospital_id=(
                hospital_id
            ),
            data=data,
            booking_source="VOICE"
        )

        try:
            send_appointment_whatsapp(
                appointment
            )
        except Exception as e:
            print(
                "Voice WhatsApp error:",
                e
            )

        try:
            send_fcm_to_hospital(
                hospital_id,
                appointment
            )
        except Exception as e:
            print(
                "Voice FCM error:",
                e
            )

        return jsonify({
            "success": True,
            "message":
                "Voice appointment booked successfully",
            "appointment":
                appointment
        })

    except Exception as e:

        print(
            "voice booking error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


# ============================================================
# GET HOSPITAL APPOINTMENTS
# ============================================================

def get_hospital_appointments(
    hospital_id
):

    if not hospital_id:
        return []

    appointments_data = (
        db.reference(
            "appointments"
        ).get()
        or {}
    )

    # --------------------------------------------------------
    # Load patient master once.
    # This is important because NEW -> OLD is persistent.
    # --------------------------------------------------------

    patients_data = (
        db.reference(
            f"patients/{hospital_id}"
        ).get()
        or {}
    )

    appointments = []

    for appointment_id, raw_appointment in (
        appointments_data.items()
    ):

        if not isinstance(
            raw_appointment,
            dict
        ):
            continue

        if raw_appointment.get(
            "hospital_id"
        ) != hospital_id:
            continue

        appointment = dict(
            raw_appointment
        )

        appointment[
            "id"
        ] = appointment_id

        mobile = normalize_mobile(
            appointment.get(
                "mobile"
            )
        )

        patient_master = (
            patients_data.get(
                mobile,
                {}
            )
            if mobile
            else {}
        )

        # ----------------------------------------------------
        # TYPE
        #
        # Patient master is the current persistent status.
        # Therefore once doctor marks OLD, future appointment
        # rows also show OLD.
        #
        # Historical charge is NOT recalculated.
        # ----------------------------------------------------

        master_status = str(
            patient_master.get(
                "patient_status",
                ""
            )
        ).upper()

        appointment_status = str(
            appointment.get(
                "patient_status",
                "NEW"
            )
        ).upper()

        if master_status in [
            "NEW",
            "OLD"
        ]:
            appointment[
                "patient_status"
            ] = master_status

        elif appointment_status in [
            "NEW",
            "OLD"
        ]:
            appointment[
                "patient_status"
            ] = appointment_status

        else:
            appointment[
                "patient_status"
            ] = "NEW"

        # ----------------------------------------------------
        # VISIT
        #
        # Appointment's stored visit_number is authoritative.
        # This prevents old records from changing.
        # ----------------------------------------------------

        stored_visit = appointment.get(
            "visit_number"
        )

        if stored_visit is None:
            stored_visit = appointment.get(
                "patient_visit"
            )

        if stored_visit is None:
            stored_visit = 1

        appointment[
            "visit_number"
        ] = safe_int(
            stored_visit,
            1
        )

        # ----------------------------------------------------
        # AMOUNT
        #
        # NEVER calculate amount again from current pricing.
        # Historical appointment amount must remain unchanged.
        # ----------------------------------------------------

        if appointment.get(
            "charge"
        ) is None:

            # Only for very old records that were created
            # before charge functionality existed.
            appointment[
                "charge"
            ] = 0

        appointment[
            "charge"
        ] = safe_float(
            appointment.get(
                "charge"
            ),
            0
        )

        appointment[
            "day_status"
        ] = get_appointment_day_status(
            appointment.get(
                "appointment_date"
            )
        )

        appointments.append(
            appointment
        )

    # --------------------------------------------------------
    # Latest appointment first
    # --------------------------------------------------------

    appointments.sort(
        key=appointment_sort_key,
        reverse=True
    )

    return appointments


# ============================================================
# APPOINTMENTS PAGE
# ============================================================

@app.route(
    "/appointments/<hospital_id>"
)
def appointments_page(
    hospital_id
):

    try:

        require_hospital_access(
            hospital_id
        )

        appointments = (
            get_hospital_appointments(
                hospital_id
            )
        )

        hospital = db.reference(
            f"hospitals/{hospital_id}"
        ).get() or {}

        return render_template(
            "appointments.html",
            appointments=appointments,
            patients=appointments,
            hospital=hospital,
            hospital_id=hospital_id
        )

    except Exception as e:

        print(
            "appointments page error:",
            e
        )

        return (
            f"Error: {e}",
            500
        )


# ============================================================
# ANALYTICS
# ============================================================

def get_hospital_analytics(
    hospital_id
):

    appointments = (
        get_hospital_appointments(
            hospital_id
        )
    )

    today = datetime.now().date()

    today_appointments = []

    upcoming = []

    past = []

    revenue = 0

    new_patients = 0

    old_patients = 0

    doctors = set()

    for appointment in appointments:

        date_value = appointment.get(
            "appointment_date"
        )

        dt = parse_date(
            date_value
        )

        if dt:

            if dt.date() == today:
                today_appointments.append(
                    appointment
                )

            elif dt.date() > today:
                upcoming.append(
                    appointment
                )

            else:
                past.append(
                    appointment
                )

        revenue += safe_float(
            appointment.get(
                "charge",
                0
            )
        )

        status = str(
            appointment.get(
                "patient_status",
                "NEW"
            )
        ).upper()

        if status == "OLD":
            old_patients += 1
        else:
            new_patients += 1

        doctor_name = str(
            appointment.get(
                "doctor_name",
                ""
            )
        ).strip()

        if doctor_name:
            doctors.add(
                doctor_name
            )

    return {

        "total_appointments":
            len(appointments),

        "today_appointments":
            len(today_appointments),

        "upcoming_appointments":
            len(upcoming),

        "past_appointments":
            len(past),

        "new_patients":
            new_patients,

        "old_patients":
            old_patients,

        "total_revenue":
            revenue,

        "doctor_count":
            len(doctors),

        "doctors":
            sorted(doctors)
    }


@app.route(
    "/api/analytics/<hospital_id>"
)
def analytics_api(
    hospital_id
):

    try:

        require_hospital_access(
            hospital_id
        )

        analytics = get_hospital_analytics(
            hospital_id
        )

        return jsonify({
            "success": True,
            "analytics":
                analytics
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@app.route(
    "/analytics/<hospital_id>"
)
def analytics_page(
    hospital_id
):

    try:

        require_hospital_access(
            hospital_id
        )

        analytics = get_hospital_analytics(
            hospital_id
        )

        return render_template(
            "analytics.html",
            analytics=analytics,
            hospital_id=hospital_id
        )

    except Exception as e:

        return (
            f"Error: {e}",
            500
        )


# ============================================================
# DASHBOARD STATS
# ============================================================

@app.route(
    "/api/dashboard-stats/<hospital_id>",
    methods=["GET"]
)
def dashboard_stats(
    hospital_id
):

    try:

        require_hospital_access(
            hospital_id
        )

        appointments = (
            get_hospital_appointments(
                hospital_id
            )
        )

        today = datetime.now().date()

        today_count = 0

        followup_count = 0

        doctor_names = set()

        for appointment in appointments:

            dt = parse_date(
                appointment.get(
                    "appointment_date"
                )
            )

            if dt and dt.date() == today:
                today_count += 1

            if appointment.get(
                "next_visit_date"
            ):
                followup_count += 1

            doctor_name = str(
                appointment.get(
                    "doctor_name",
                    ""
                )
            ).strip()

            if doctor_name:
                doctor_names.add(
                    doctor_name
                )

        # If request reached Firebase successfully,
        # system is operational.
        system_status = "Live"
        availability = "100%"

        return jsonify({

            "success": True,

            "today_appointments":
                today_count,

            "doctor_count":
                len(doctor_names),

            "followups":
                followup_count,

            "system_status":
                system_status,

            "availability":
                availability
        })

    except Exception as e:

        print(
            "dashboard stats error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================================
# FOLLOWUPS PAGE
# ============================================================

@app.route(
    "/followups/<hospital_id>"
)
def followups_page(
    hospital_id
):

    try:

        require_hospital_access(
            hospital_id
        )

        appointments = (
            get_hospital_appointments(
                hospital_id
            )
        )

        followups = []

        for appointment in appointments:

            next_visit_date = (
                appointment.get(
                    "next_visit_date"
                )
            )

            if not next_visit_date:
                continue

            followup = dict(
                appointment
            )

            followup[
                "next_visit_date"
            ] = next_visit_date

            followups.append(
                followup
            )

        followups.sort(
            key=lambda x: (
                parse_date(
                    x.get(
                        "next_visit_date"
                    )
                )
                or datetime.max
            )
        )

        return render_template(
            "followups.html",
            followups=followups,
            appointments=appointments,
            hospital_id=hospital_id
        )

    except Exception as e:

        return (
            f"Error: {e}",
            500
        )


# ============================================================
# SAVE FOLLOWUP
# ============================================================

@app.route(
    "/save_followup",
    methods=["POST"]
)
def save_followup():

    try:

        decoded = verify_firebase_token()

        hospital_id = decoded.get(
            "uid"
        )

        data = request.get_json(
            silent=True
        ) or {}

        appointment_id = data.get(
            "appointment_id"
        )

        if not appointment_id:
            return jsonify({
                "success": False,
                "message":
                    "Appointment ID required"
            }), 400

        appointment_ref = db.reference(
            f"appointments/{appointment_id}"
        )

        appointment = (
            appointment_ref.get()
        )

        if not appointment:
            return jsonify({
                "success": False,
                "message":
                    "Appointment not found"
            }), 404

        if appointment.get(
            "hospital_id"
        ) != hospital_id:
            return jsonify({
                "success": False,
                "message":
                    "Unauthorized"
            }), 403

        next_visit_date = data.get(
            "next_visit_date"
        )

        notes = data.get(
            "notes",
            ""
        )

        update_data = {

            "next_visit_date":
                next_visit_date,

            "followup_notes":
                notes,

            "followup_created_at":
                utc_now_iso()
        }

        appointment_ref.update(
            update_data
        )

        updated = dict(
            appointment
        )

        updated.update(
            update_data
        )

        # ----------------------------------------------------
        # WhatsApp follow-up reminder
        # ----------------------------------------------------

        try:

            send_followup_whatsapp(
                updated
            )

        except Exception as e:

            print(
                "Followup WhatsApp error:",
                e
            )

        # ----------------------------------------------------
        # FCM
        # ----------------------------------------------------

        try:

            send_fcm_to_hospital(
                hospital_id,
                updated,
                title="Follow-up Reminder"
            )

        except Exception as e:

            print(
                "Followup FCM error:",
                e
            )

        return jsonify({
            "success": True,
            "message":
                "Follow-up saved successfully",
            "followup":
                updated
        })

    except Exception as e:

        print(
            "save followup error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================================
# FCM TOKEN
# ============================================================

@app.route(
    "/save_token",
    methods=["POST"]
)
def save_token():

    try:

        decoded = verify_firebase_token()

        uid = decoded.get(
            "uid"
        )

        data = request.get_json(
            silent=True
        ) or {}

        token = data.get(
            "token"
        )

        if not token:
            return jsonify({
                "success": False,
                "message":
                    "Token required"
            }), 400

        db.reference(
            f"notification_tokens/{uid}/{token}"
        ).set({
            "token": token,
            "created_at":
                utc_now_iso()
        })

        return jsonify({
            "success": True,
            "message":
                "Notification token saved"
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================================
# FCM SEND
# ============================================================

def send_fcm_to_hospital(
    hospital_id,
    appointment,
    title="New Appointment"
):

    tokens_data = db.reference(
        f"notification_tokens/{hospital_id}"
    ).get() or {}

    if not tokens_data:
        return

    patient_name = appointment.get(
        "patient_name",
        "Patient"
    )

    doctor_name = appointment.get(
        "doctor_name",
        ""
    )

    body = (
        f"{patient_name} booked an appointment"
    )

    if doctor_name:
        body += (
            f" with Dr. {doctor_name}"
        )

    for token_key, token_info in (
        tokens_data.items()
    ):

        token = token_key

        if isinstance(
            token_info,
            dict
        ):
            token = token_info.get(
                "token",
                token_key
            )

        if not token:
            continue

        try:

            message = messaging.Message(

                notification=messaging.Notification(
                    title=title,
                    body=body
                ),

                data={

                    "type":
                        "appointment",

                    "appointment_id":
                        str(
                            appointment.get(
                                "id",
                                ""
                            )
                        ),

                    "patient_name":
                        str(
                            patient_name
                        )
                },

                token=token
            )

            messaging.send(
                message
            )

        except Exception as e:

            print(
                "FCM token error:",
                e
            )


# ============================================================
# AISENSY WHATSAPP
# ============================================================

def send_appointment_whatsapp(
    appointment
):

    if not AISENSY_API_KEY:
        print(
            "AISENSY_API_KEY not configured"
        )
        return None

    mobile = format_whatsapp_number(
        appointment.get(
            "mobile"
        )
    )

    if not mobile:
        return None

    patient_name = appointment.get(
        "patient_name",
        ""
    )

    appointment_date = appointment.get(
        "appointment_date",
        ""
    )

    appointment_time = appointment.get(
        "appointment_time",
        ""
    )

    doctor_name = appointment.get(
        "doctor_name",
        ""
    )

    # --------------------------------------------------------
    # Approved template:
    # mediqueue_appointment_confirmation
    # --------------------------------------------------------

    payload = {

        "apiKey":
            AISENSY_API_KEY,

        "campaignName":
            "MediQueue Appointment Confirmation",

        "destination":
            mobile,

        "userName":
            patient_name,

        "templateParams": [

            patient_name,

            appointment_date,

            appointment_time,

            doctor_name
        ]
    }

    headers = {
        "Content-Type":
            "application/json"
    }

    response = requests.post(
        AISENSY_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    print(
        "AiSensy appointment:",
        response.status_code,
        response.text
    )

    return response


# ============================================================
# AISENSY FOLLOWUP
# ============================================================

def send_followup_whatsapp(
    appointment
):

    if not AISENSY_API_KEY:
        return None

    mobile = format_whatsapp_number(
        appointment.get(
            "mobile"
        )
    )

    if not mobile:
        return None

    patient_name = appointment.get(
        "patient_name",
        ""
    )

    next_visit_date = appointment.get(
        "next_visit_date",
        ""
    )

    doctor_name = appointment.get(
        "doctor_name",
        ""
    )

    notes = appointment.get(
        "followup_notes",
        ""
    )

    payload = {

        "apiKey":
            AISENSY_API_KEY,

        "campaignName":
            "MediQueue Follow-up Reminder",

        "destination":
            mobile,

        "userName":
            patient_name,

        "templateParams": [

            patient_name,

            next_visit_date,

            doctor_name,

            notes
        ]
    }

    headers = {
        "Content-Type":
            "application/json"
    }

    response = requests.post(
        AISENSY_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    print(
        "AiSensy followup:",
        response.status_code,
        response.text
    )

    return response


# ============================================================
# WHATSAPP WEBHOOK
# ============================================================

@app.route(
    "/whatsapp/webhook",
    methods=[
        "GET",
        "POST"
    ]
)
def whatsapp_webhook():

    if request.method == "GET":

        return jsonify({
            "success": True,
            "message":
                "WhatsApp webhook active"
        })

    try:

        payload = request.get_json(
            silent=True
        ) or {}

        print(
            "WhatsApp webhook:",
            json.dumps(
                payload,
                indent=2
            )
        )

        return jsonify({
            "success": True
        })

    except Exception as e:

        print(
            "WhatsApp webhook error:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    firebase_status = "OK"

    try:
        db.reference(
            ".info/connected"
        ).get()

    except Exception as e:

        firebase_status = (
            f"ERROR: {e}"
        )

    return jsonify({

        "status":
            "ok",

        "service":
            "Statusly",

        "firebase":
            firebase_status,

        "time":
            utc_now_iso()
    })


# ============================================================
# FAVICON
# ============================================================

@app.route("/favicon.ico")
def favicon():
    return "", 204


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "success": False,
        "message":
            "Route not found"
    }), 404


@app.errorhandler(500)
def internal_error(error):

    return jsonify({
        "success": False,
        "message":
            "Internal server error"
    }), 500


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
