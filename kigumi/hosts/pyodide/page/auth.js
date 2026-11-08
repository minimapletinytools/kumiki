// Where sign-in comes back to (agent/account.js redirectTo). Hands the link to the Kigumi tab that
// asked (page/transport.js); with none listening, keeps it and goes back to Kigumi, which finishes it.
(function () {
    'use strict';
    const url = window.location.href;
    const message = document.getElementById('message');
    let received = false;
    if ('BroadcastChannel' in window) {
        const channel = new BroadcastChannel('kigumi-auth');
        channel.onmessage = (event) => {
            if (event.data && event.data.type === 'received') {
                received = true;
                message.textContent = 'Signed in. You can close this tab and go back to Kigumi.';
                window.close();
            }
        };
        channel.postMessage({ type: 'authLink', url });
    }
    setTimeout(() => {
        if (received) return;
        try {
            localStorage.setItem('kigumi.web.authLink', url);
        } catch (_error) {
            message.textContent = "Couldn't finish signing in: this browser won't keep it. Go back to Kigumi and try again.";
            return;
        }
        window.location.replace(new URL('index.html', window.location.href).href);
    }, 1500);
})();
