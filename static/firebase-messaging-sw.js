importScripts("https://www.gstatic.com/firebasejs/12.17.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/12.17.0/firebase-messaging-compat.js");

firebase.initializeApp({
    apiKey: "AIzaSyDbHoUVO_oXHCnY040sBLOiXVS6s6xJEb8",
    authDomain: "hospital-57fc8.firebaseapp.com",
    databaseURL: "https://hospital-57fc8-default-rtdb.firebaseio.com",
    projectId: "hospital-57fc8",
    storageBucket: "hospital-57fc8.firebasestorage.app",
    messagingSenderId: "711314420912",
    appId: "1:711314420912:web:14ec889664980679a13775"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {

    console.log("Background Message:", payload);

    const title =
        payload.notification?.title ||
        payload.data?.title ||
        "Hospital Reminder";

    const options = {
        body:
            payload.notification?.body ||
            payload.data?.body ||
            "Follow-up Reminder",

        icon: "/static/icon.png",

        badge: "/static/icon.png",

        data: payload.data
    };

    self.registration.showNotification(title, options);

});

self.addEventListener("notificationclick", function(event) {

    event.notification.close();

    event.waitUntil(
        clients.openWindow("/")
    );

});
