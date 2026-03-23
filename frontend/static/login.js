async function login() {
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    const errorEl = document.getElementById("error-msg");
    errorEl.innerText = "";

    if (!username || !password) {
        errorEl.innerText = "Bitte Benutzername und Passwort eingeben.";
        return;
    }

    const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
    });

    const data = await res.json();

    if (res.ok) {
        window.location.href = "/";
    } else {
        errorEl.innerText = data.error || "Login fehlgeschlagen.";
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById("login-button").addEventListener("click", login);
});
