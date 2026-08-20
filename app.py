<!DOCTYPE html>
<html lang="en">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>MediQueue Hospital Dashboard</title>

    <style>

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
        }

        body {

            min-height: 100vh;

            background:
                linear-gradient(
                    rgba(0,0,0,0.65),
                    rgba(0,0,0,0.65)
                ),
                url("https://images.unsplash.com/photo-1586773860418-d37222d8fce3")
                center center / cover fixed no-repeat;

        }

        .layout {

            min-height: 100vh;

            display: flex;

        }


        /* ==============================
           SIDEBAR
        ============================== */

        .sidebar {

            width: 240px;

            min-height: 100vh;

            position: fixed;

            left: 0;
            top: 0;
            bottom: 0;

            padding: 22px;

            background:
                rgba(0,0,0,0.90);

            color: white;

            overflow-y: auto;

        }

        .logo {

            text-align: center;

            font-size: 22px;

            font-weight: bold;

            margin-bottom: 25px;

        }

        .sidebar button {

            width: 100%;

            padding: 13px;

            margin: 6px 0;

            border: none;

            border-radius: 8px;

            background: #3498db;

            color: white;

            font-size: 15px;

            cursor: pointer;

            transition: 0.2s;

        }

        .sidebar button:hover {

            background: #217dbb;

            transform: translateY(-1px);

        }

        .logout {

            background: #e74c3c !important;

            margin-top: 25px !important;

        }

        .logout:hover {

            background: #c0392b !important;

        }


        /* ==============================
           CONTENT
        ============================== */

        .content {

            width: calc(100% - 240px);

            margin-left: 240px;

            min-height: 100vh;

            padding: 30px;

            color: white;

        }


        /* ==============================
           TOPBAR
        ============================== */

        .topbar {

            display: flex;

            justify-content: space-between;

            align-items: center;

            gap: 15px;

            flex-wrap: wrap;

            margin-bottom: 25px;

        }

        .topbar h1 {

            font-size: 30px;

        }

        .hospital-display {

            padding: 10px 16px;

            border-radius: 8px;

            background:
                rgba(255,255,255,0.14);

            backdrop-filter: blur(10px);

        }


        /* ==============================
           CARD
        ============================== */

        .card {

            background:
                rgba(255,255,255,0.12);

            backdrop-filter: blur(14px);

            padding: 25px;

            border-radius: 15px;

            margin-bottom: 20px;

            box-shadow:
                0 10px 30px rgba(0,0,0,0.30);

        }

        .card h2 {

            margin-bottom: 18px;

        }


        /* ==============================
           FORM
        ============================== */

        input,
        textarea {

            width: 100%;

            padding: 13px;

            margin: 8px 0;

            border: none;

            outline: none;

            border-radius: 8px;

            background: white;

            color: #222;

            font-size: 15px;

        }

        input:disabled {

            background: #ddd;

            color: #555;

        }

        textarea {

            min-height: 110px;

            resize: vertical;

        }


        /* ==============================
           BUTTONS
        ============================== */

        .save-btn {

            background: #27ae60;

            color: white;

            border: none;

            border-radius: 8px;

            padding: 13px 20px;

            margin-top: 12px;

            cursor: pointer;

            font-size: 15px;

        }

        .save-btn:hover {

            background: #1f8a4c;

        }

        .add-btn {

            background: #8e44ad;

            color: white;

            border: none;

            border-radius: 8px;

            padding: 12px 18px;

            margin-top: 10px;

            cursor: pointer;

        }

        .add-btn:hover {

            background: #71368a;

        }


        /* ==============================
           DOCTOR
        ============================== */

        .doctor-box {

            background:
                rgba(255,255,255,0.09);

            border-radius: 10px;

            padding: 18px;

            margin-bottom: 15px;

        }

        .doctor-header {

            display: flex;

            justify-content: space-between;

            align-items: center;

            margin-bottom: 10px;

        }

        .remove-btn {

            background: #e74c3c;

            color: white;

            border: none;

            border-radius: 6px;

            padding: 7px 12px;

            cursor: pointer;

        }

        .remove-btn:hover {

            background: #c0392b;

        }


        /* ==============================
           STATUS
        ============================== */

        #status {

            display: none;

            padding: 13px;

            margin-top: 15px;

            border-radius: 8px;

            background:
                rgba(255,255,255,0.15);

        }


        /* ==============================
           LOADING
        ============================== */

        #loading {

            position: fixed;

            inset: 0;

            background:
                rgba(0,0,0,0.85);

            display: flex;

            align-items: center;

            justify-content: center;

            z-index: 9999;

            color: white;

            font-size: 20px;

        }


        /* ==============================
           MOBILE
        ============================== */

        @media(max-width:768px) {

            .sidebar {

                position: relative;

                width: 100%;

                min-height: auto;

            }

            .layout {

                display: block;

            }

            .content {

                width: 100%;

                margin-left: 0;

                padding: 20px;

            }

            .sidebar button {

                width: calc(50% - 5px);

            }

            .logo {

                width: 100%;

            }

        }

    </style>

</head>


<body>


<div id="loading">
    Checking login...
</div>


<div class="layout">


    <!-- ==============================
         SIDEBAR
    ============================== -->

    <aside class="sidebar">

        <div class="logo">
            🏥 MediQueue
        </div>


        <button onclick="showSection('hospital')">
            🏥 Hospital
        </button>


        <button onclick="showSection('doctor')">
            👨‍⚕️ Doctors
        </button>


        <button onclick="openAppointments()">
            📅 Appointments
        </button>


        <button onclick="openFollowups()">
            🔄 Follow-ups
        </button>


        <button onclick="openHospitalPage()">
            🌐 View Hospital
        </button>


        <button
            class="logout"
            onclick="logout()"
        >
            🚪 Logout
        </button>

    </aside>



    <!-- ==============================
         CONTENT
    ============================== -->

    <main class="content">


        <div class="topbar">

            <h1>
                Hospital Dashboard
            </h1>

            <div
                id="hospitalNameDisplay"
                class="hospital-display"
            >
                Loading...
            </div>

        </div>



        <!-- ==============================
             HOSPITAL
        ============================== -->

        <section
            id="hospital"
            class="card section"
        >

            <h2>
                🏥 Hospital Details
            </h2>


            <input
                id="hospital_uid"
                placeholder="Firebase Hospital UID"
                disabled
            >


            <input
                id="hospital_name"
                placeholder="Hospital Name"
            >


            <input
                id="date"
                type="date"
            >


            <input
                id="open_time"
                type="time"
            >


            <input
                id="close_time"
                type="time"
            >


            <textarea
                id="info"
                placeholder="Hospital Information"
            ></textarea>


            <button
                class="save-btn"
                onclick="saveHospital()"
            >
                💾 Save Hospital
            </button>


            <div id="status"></div>

        </section>



        <!-- ==============================
             DOCTORS
        ============================== -->

        <section
            id="doctor"
            class="card section"
            style="display:none;"
        >

            <h2>
                👨‍⚕️ Doctor Details
            </h2>


            <div id="doctor-section">


                <div class="doctor-box">

                    <div class="doctor-header">

                        <h3>
                            Doctor 1
                        </h3>

                    </div>


                    <input
                        class="doctor_name"
                        placeholder="Doctor Name"
                    >


                    <input
                        class="specialization"
                        placeholder="Specialization"
                    >


                    <input
                        class="opd_time"
                        placeholder="OPD Time"
                    >


                    <textarea
                        class="doctor_info"
                        placeholder="Doctor Information"
                    ></textarea>

                </div>


            </div>


            <button
                class="add-btn"
                onclick="addDoctor()"
            >
                + Add Doctor
            </button>


            <br>


            <button
                class="save-btn"
                onclick="saveHospital()"
            >
                💾 Save Hospital & Doctors
            </button>

        </section>


    </main>

</div>



<script type="module">


/* ============================================================
   FIREBASE
============================================================ */

import {
    initializeApp
}
from
"https://www.gstatic.com/firebasejs/12.15.0/firebase-app.js";


import {
    getAuth,
    onAuthStateChanged,
    signOut
}
from
"https://www.gstatic.com/firebasejs/12.15.0/firebase-auth.js";


/* ============================================================
   FIREBASE CONFIG
============================================================ */

const firebaseConfig = {

    apiKey:
        "AIzaSyDbHoUVO_oXHCnY040sBLOiXVS6s6xJEb8",

    authDomain:
        "hospital-57fc8.firebaseapp.com",

    databaseURL:
        "https://hospital-57fc8-default-rtdb.firebaseio.com",

    projectId:
        "hospital-57fc8",

    storageBucket:
        "hospital-57fc8.firebasestorage.app",

    messagingSenderId:
        "711314420912",

    appId:
        "1:711314420912:web:14ec889664980679a13775"

};


const app =
    initializeApp(firebaseConfig);


const auth =
    getAuth(app);



/* ============================================================
   CURRENT USER
============================================================ */

let currentUser = null;

let doctorCount = 1;



/* ============================================================
   AUTHENTICATION
============================================================ */

onAuthStateChanged(
    auth,
    async (user) => {

        console.log(
            "AUTH STATE:",
            user
        );


        if (!user) {

            window.location.href =
                "/login-page";

            return;

        }


        currentUser = user;


        try {

            /*
             * Get fresh Firebase token
             */

            const token =
                await user.getIdToken(true);


            if (!token) {

                window.location.href =
                    "/login-page";

                return;

            }


            /*
             * Check subscription
             */

            const response =
                await fetch(
                    "/check-subscription",
                    {

                        method: "POST",

                        headers: {

                            "Authorization":
                                "Bearer " + token,

                            "Content-Type":
                                "application/json"

                        }

                    }
                );


            const data =
                await response.json();


            console.log(
                "SUBSCRIPTION:",
                data
            );


            if (!response.ok) {

                alert(
                    data.error ||
                    "Unable to verify subscription."
                );

                window.location.href =
                    "/login-page";

                return;

            }


            if (data.active !== true) {

                alert(
                    "Your subscription has expired or is not active."
                );

                window.location.href =
                    "/payment";

                return;

            }


            /*
             * IMPORTANT
             *
             * Firebase UID is the ID used by:
             *
             * /save_hospital
             *
             * /hospital/<uid>
             *
             * /appointments/<uid>
             *
             * /followups/<uid>
             */

            const uid =
                user.uid;


            localStorage.setItem(
                "uid",
                uid
            );


            document.getElementById(
                "hospital_uid"
            ).value = uid;


            /*
             * Load hospital from backend
             */

            await loadHospital(uid);


            document.getElementById(
                "loading"
            ).style.display =
                "none";


        }
        catch(error) {

            console.error(
                "DASHBOARD ERROR:",
                error
            );

            alert(
                "Unable to load dashboard."
            );

            window.location.href =
                "/login-page";

        }

    }
);



/* ============================================================
   LOAD HOSPITAL
============================================================ */

async function loadHospital(uid) {

    try {

        /*
         * We use an API request here.
         *
         * Add the route below to Flask:
         *
         * /api/hospital/<uid>
         */

        const response =
            await fetch(
                `/api/hospital/${encodeURIComponent(uid)}`
            );


        if (!response.ok) {

            console.log(
                "No saved hospital yet."
            );

            document.getElementById(
                "hospitalNameDisplay"
            ).innerText =
                "Hospital";

            return;

        }


        const hospital =
            await response.json();


        console.log(
            "HOSPITAL DATA:",
            hospital
        );


        document.getElementById(
            "hospital_name"
        ).value =
            hospital.hospital_name || "";


        document.getElementById(
            "date"
        ).value =
            hospital.date || "";


        document.getElementById(
            "open_time"
        ).value =
            hospital.open_time || "";


        document.getElementById(
            "close_time"
        ).value =
            hospital.close_time || "";


        document.getElementById(
            "info"
        ).value =
            hospital.info || "";


        document.getElementById(
            "hospitalNameDisplay"
        ).innerText =
            hospital.hospital_name ||
            "Hospital";


        /*
         * Load doctors
         */

        if (
            Array.isArray(
                hospital.doctors
            )
        ) {

            loadDoctors(
                hospital.doctors
            );

        }


    }
    catch(error) {

        console.error(
            "LOAD HOSPITAL ERROR:",
            error
        );

    }

}



/* ============================================================
   LOAD DOCTORS
============================================================ */

function loadDoctors(doctors) {

    const container =
        document.getElementById(
            "doctor-section"
        );


    container.innerHTML = "";


    doctorCount = 0;


    doctors.forEach(
        (doctor) => {

            doctorCount++;


            const box =
                document.createElement(
                    "div"
                );


            box.className =
                "doctor-box";


            box.innerHTML = `

                <div class="doctor-header">

                    <h3>
                        Doctor ${doctorCount}
                    </h3>

                    <button
                        type="button"
                        class="remove-btn"
                    >
                        Remove
                    </button>

                </div>

                <input
                    class="doctor_name"
                    placeholder="Doctor Name"
                    value="${escapeHTML(
                        doctor.doctor_name || ""
                    )}"
                >

                <input
                    class="specialization"
                    placeholder="Specialization"
                    value="${escapeHTML(
                        doctor.specialization || ""
                    )}"
                >

                <input
                    class="opd_time"
                    placeholder="OPD Time"
                    value="${escapeHTML(
                        doctor.opd_time || ""
                    )}"
                >

                <textarea
                    class="doctor_info"
                    placeholder="Doctor Information"
                >${escapeHTML(
                    doctor.doctor_info || ""
                )}</textarea>

            `;


            box.querySelector(
                ".remove-btn"
            ).onclick =
                () => {

                    box.remove();

                };


            container.appendChild(
                box
            );

        }
    );


    if (doctorCount === 0) {

        addDoctor();

    }

}



/* ============================================================
   HTML ESCAPE
============================================================ */

function escapeHTML(value) {

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

}



/* ============================================================
   SHOW SECTION
============================================================ */

window.showSection =
function(id) {

    document
        .querySelectorAll(".section")
        .forEach(
            section => {

                section.style.display =
                    "none";

            }
        );


    const section =
        document.getElementById(id);


    if (section) {

        section.style.display =
            "block";

    }

};



/* ============================================================
   ADD DOCTOR
============================================================ */

window.addDoctor =
function() {

    doctorCount++;


    const container =
        document.getElementById(
            "doctor-section"
        );


    const box =
        document.createElement(
            "div"
        );


    box.className =
        "doctor-box";


    box.innerHTML = `

        <div class="doctor-header">

            <h3>
                Doctor ${doctorCount}
            </h3>

            <button
                type="button"
                class="remove-btn"
            >
                Remove
            </button>

        </div>

        <input
            class="doctor_name"
            placeholder="Doctor Name"
        >

        <input
            class="specialization"
            placeholder="Specialization"
        >

        <input
            class="opd_time"
            placeholder="OPD Time"
        >

        <textarea
            class="doctor_info"
            placeholder="Doctor Information"
        ></textarea>

    `;


    box.querySelector(
        ".remove-btn"
    ).onclick =
        () => {

            box.remove();

        };


    container.appendChild(
        box
    );

};



/* ============================================================
   SAVE HOSPITAL
============================================================ */

window.saveHospital =
async function() {

    try {

        if (!currentUser) {

            alert(
                "Login session expired."
            );

            window.location.href =
                "/login-page";

            return;

        }


        /*
         * ALWAYS use Firebase UID.
         */

        const uid =
            currentUser.uid;


        const token =
            await currentUser.getIdToken(true);


        /*
         * FormData
         */

        const formData =
            new FormData();


        formData.append(
            "uid",
            uid
        );


        formData.append(
            "hospital_name",
            document.getElementById(
                "hospital_name"
            ).value.trim()
        );


        formData.append(
            "date",
            document.getElementById(
                "date"
            ).value
        );


        formData.append(
            "open_time",
            document.getElementById(
                "open_time"
            ).value
        );


        formData.append(
            "close_time",
            document.getElementById(
                "close_time"
            ).value
        );


        formData.append(
            "info",
            document.getElementById(
                "info"
            ).value.trim()
        );


        /*
         * Doctors
         */

        const names =
            document.querySelectorAll(
                ".doctor_name"
            );


        const specs =
            document.querySelectorAll(
                ".specialization"
            );


        const times =
            document.querySelectorAll(
                ".opd_time"
            );


        const infos =
            document.querySelectorAll(
                ".doctor_info"
            );


        names.forEach(
            (element, index) => {

                formData.append(
                    "doctor_name",
                    element.value.trim()
                );


                formData.append(
                    "specialization",
                    specs[index].value.trim()
                );


                formData.append(
                    "opd_time",
                    times[index].value.trim()
                );


                formData.append(
                    "doctor_info",
                    infos[index].value.trim()
                );

            }
        );


        /*
         * Save
         */

        showStatus(
            "Saving hospital...",
            false
        );


        const response =
            await fetch(
                "/save_hospital",
                {

                    method: "POST",

                    headers: {

                        "Authorization":
                            "Bearer " + token

                    },

                    body: formData

                }
            );


        const data =
            await response.json();


        console.log(
            "SAVE RESPONSE:",
            data
        );


        if (response.status === 403) {

            alert(
                data.error ||
                "Subscription expired."
            );

            window.location.href =
                "/payment";

            return;

        }


        if (!response.ok) {

            showStatus(
                data.error ||
                "Unable to save hospital.",
                true
            );

            return;

        }


        /*
         * Save name locally only for display.
         */

        const hospitalName =
            document.getElementById(
                "hospital_name"
            ).value.trim();


        localStorage.setItem(
            "hospitalName",
            hospitalName
        );


        document.getElementById(
            "hospitalNameDisplay"
        ).innerText =
            hospitalName ||
            "Hospital";


        showStatus(
            "Hospital saved successfully.",
            false
        );


        /*
         * IMPORTANT
         *
         * Correct URL:
         *
         * /hospital/FIREBASE_UID
         *
         * NOT:
         *
         * /hospitalFIREBASE_UID
         */

        setTimeout(
            () => {

                window.location.href =
                    `/hospital/${encodeURIComponent(uid)}`;

            },
            700
        );


    }
    catch(error) {

        console.error(
            "SAVE HOSPITAL ERROR:",
            error
        );


        showStatus(
            "Unable to connect to server.",
            true
        );

    }

};



/* ============================================================
   STATUS
============================================================ */

function showStatus(message, error) {

    const status =
        document.getElementById(
            "status"
        );


    status.style.display =
        "block";


    status.innerText =
        message;


    status.style.background =
        error
            ? "rgba(231,76,60,0.35)"
            : "rgba(39,174,96,0.35)";

}



/* ============================================================
   VIEW HOSPITAL
============================================================ */

window.openHospitalPage =
function() {

    if (!currentUser) {

        window.location.href =
            "/login-page";

        return;

    }


    const uid =
        currentUser.uid;


    /*
     * CORRECT
     */

    window.location.href =
        `/hospital/${encodeURIComponent(uid)}`;

};



/* ============================================================
   APPOINTMENTS
============================================================ */

window.openAppointments =
function() {

    if (!currentUser) {

        window.location.href =
            "/login-page";

        return;

    }


    const uid =
        currentUser.uid;


    window.location.href =
        `/appointments/${encodeURIComponent(uid)}`;

};



/* ============================================================
   FOLLOWUPS
============================================================ */

window.openFollowups =
function() {

    if (!currentUser) {

        window.location.href =
            "/login-page";

        return;

    }


    const uid =
        currentUser.uid;


    window.location.href =
        `/followups/${encodeURIComponent(uid)}`;

};



/* ============================================================
   LOGOUT
============================================================ */

window.logout =
async function() {

    try {

        await signOut(auth);


        localStorage.removeItem(
            "uid"
        );

        localStorage.removeItem(
            "hospitalName"
        );

        localStorage.removeItem(
            "hospitalId"
        );


        window.location.href =
            "/login-page";

    }
    catch(error) {

        console.error(
            "LOGOUT ERROR:",
            error
        );

        alert(
            "Logout failed."
        );

    }

};



/* ============================================================
   DEFAULT
============================================================ */

showSection(
    "hospital"
);

</script>

</body>

</html>
