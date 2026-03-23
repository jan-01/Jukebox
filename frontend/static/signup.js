function checkPassword(pw) {
    const set = (id, ok) => document.getElementById(id).classList.toggle('ok', ok);
    set('hint-length',  pw.length >= 8);
    set('hint-upper',   /[A-Z]/.test(pw));
    set('hint-lower',   /[a-z]/.test(pw));
    set('hint-digit',   /\d/.test(pw));
    set('hint-special', /[!@#$%^&*()\-_=+\[\]{};:'",.<>?/\\|`~]/.test(pw));
}

function showError(text) {
    const el = document.getElementById("error-msg");
    el.textContent = text;
    el.classList.remove("hidden");
}

function showError409(username) {
    const el = document.getElementById("error-msg");
    el.textContent = '';

    const strong = document.createElement('strong');
    strong.textContent = `„${username}" existiert bereits.`;

    const link = document.createElement('a');
    link.href = '/login';
    link.textContent = 'Jetzt einloggen →';

    el.appendChild(strong);
    el.appendChild(document.createElement('br'));
    el.append('Diesen Benutzernamen gibt es schon. ');
    el.appendChild(link);
    el.classList.remove("hidden");
}

async function signup() {
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    const errorEl = document.getElementById("error-msg");
    errorEl.classList.add("hidden");

    if (!username || !password) {
        showError("Bitte Benutzername und Passwort eingeben.");
        return;
    }

    const res = await fetch("/api/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
    });

    const data = await res.json();

    if (res.ok) {
        window.location.href = "/";
    } else if (res.status === 409) {
        showError409(username);
    } else {
        showError(data.error || "Registrierung fehlgeschlagen.");
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById("password").addEventListener("input", (e) => checkPassword(e.target.value));
    document.getElementById("signup-button").addEventListener("click", signup);
});
