let currentUserId = null;
let showingMyReviews = false;

document.addEventListener('DOMContentLoaded', async () => {
    const appId = "default-app-id";
    const API_ENDPOINT = "/api/reviews";

    // --- Get current user ---
    try {
        const meRes = await fetch('/api/me');
        if (!meRes.ok) { window.location.href = '/login'; return; }
        const me = await meRes.json();
        currentUserId = me.username;
    } catch (e) {
        window.location.href = '/login';
        return;
    }

    document.getElementById('loading-view').classList.add('hidden');
    document.getElementById('main-view').classList.remove('hidden');
    document.getElementById('user-info').textContent = `Eingeloggt als: ${currentUserId}`;

    // --- Confirm Modal ---
    function showConfirmModal(onConfirm) {
        const modal = document.getElementById('confirm-modal');
        modal.classList.remove('hidden');

        function cleanup() {
            modal.classList.add('hidden');
            document.getElementById('confirm-modal-ok').removeEventListener('click', handleOk);
            document.getElementById('confirm-modal-cancel').removeEventListener('click', handleCancel);
            modal.removeEventListener('click', handleBackdrop);
        }
        function handleOk() { cleanup(); onConfirm(); }
        function handleCancel() { cleanup(); }
        function handleBackdrop(e) { if (e.target === modal) cleanup(); }

        document.getElementById('confirm-modal-ok').addEventListener('click', handleOk);
        document.getElementById('confirm-modal-cancel').addEventListener('click', handleCancel);
        modal.addEventListener('click', handleBackdrop);
    }

    // --- Toast notifications ---
    function showToast(msg, isError = false) {
        const toast = document.createElement('div');
        toast.textContent = msg;
        toast.className = 'toast ' + (isError ? 'toast-error' : 'toast-success');
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 500);
        }, 3000);
    }

    // --- Star rating (generic, works for any container/input pair) ---
    function setupStarRating(containerId, inputId) {
        const container = document.getElementById(containerId);
        const input = document.getElementById(inputId);
        const currentVal = parseInt(input.value) || 0;
        container.innerHTML = '';
        for (let i = 1; i <= 5; i++) {
            const span = document.createElement('span');
            span.className = 'star-icon text-gray-300 text-2xl';
            span.innerHTML = '★';
            span.setAttribute('role', 'button');
            span.setAttribute('tabindex', '0');
            span.setAttribute('aria-label', `${i} Stern${i > 1 ? 'e' : ''}`);
            span.addEventListener('mouseover', () => updateStars(i));
            span.addEventListener('mouseout', () => updateStars(parseInt(input.value) || 0));
            span.addEventListener('click', () => { input.value = i; updateStars(i); });
            span.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { input.value = i; updateStars(i); }
            });
            container.appendChild(span);
        }
        function updateStars(n) {
            Array.from(container.children).forEach((s, idx) => {
                s.classList.toggle('text-yellow-400', idx < n);
                s.classList.toggle('text-gray-300', idx >= n);
            });
        }
        updateStars(currentVal);
    }

    // --- Review card ---
    function createReviewCard(r) {
        const isOwner = r.userId === currentUserId;
        const stars = Math.min(5, Math.max(0, parseInt(r.stars) || 0));

        const div = document.createElement('div');
        div.className = 'bg-white p-5 border-l-4 border-indigo-500 rounded-lg shadow-md';

        // Header row
        const header = document.createElement('div');
        header.className = 'flex justify-between items-start mb-2';

        const title = document.createElement('h3');
        title.className = 'font-bold text-gray-900 text-lg';
        title.textContent = r.title;

        const controls = document.createElement('div');
        controls.className = 'flex items-center gap-2 ml-4 flex-shrink-0';

        const filledStars = document.createElement('span');
        filledStars.className = 'text-yellow-400';
        filledStars.textContent = '★'.repeat(stars);

        const emptyStars = document.createElement('span');
        emptyStars.className = 'text-gray-300';
        emptyStars.textContent = '☆'.repeat(5 - stars);

        controls.appendChild(filledStars);
        controls.appendChild(emptyStars);

        if (isOwner) {
            const editBtn = document.createElement('button');
            editBtn.className = 'edit-btn bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600 text-sm';
            editBtn.title = 'Bearbeiten';
            editBtn.textContent = '✏️';
            editBtn.addEventListener('click', () => openEditModal(r));

            const delBtn = document.createElement('button');
            delBtn.className = 'del-btn bg-red-500 text-white px-2 py-1 rounded hover:bg-red-600 text-sm';
            delBtn.title = 'Löschen';
            delBtn.textContent = '❌';
            delBtn.addEventListener('click', () => {
                showConfirmModal(async () => {
                    const res = await fetch(`${API_ENDPOINT}/${r.id}`, { method: 'DELETE' });
                    if (res.ok) {
                        showToast('Review gelöscht!');
                        fetchReviews();
                    } else {
                        const err = await res.json().catch(() => ({}));
                        showToast(err.error || 'Löschen fehlgeschlagen.', true);
                    }
                });
            });

            controls.appendChild(editBtn);
            controls.appendChild(delBtn);
        }

        header.appendChild(title);
        header.appendChild(controls);

        // Body
        const body = document.createElement('div');

        const reviewText = document.createElement('p');
        reviewText.className = 'text-gray-700 mb-2';
        reviewText.textContent = r.reviewText;

        const meta = document.createElement('p');
        meta.className = 'text-xs text-gray-400';
        const authorStrong = document.createElement('strong');
        authorStrong.textContent = r.userId;
        meta.append('Von: ');
        meta.appendChild(authorStrong);
        meta.append(' \u00a0|\u00a0 Erstellt: ' + new Date(r.createdAt).toLocaleString('de-DE'));
        if (r.updatedAt) {
            meta.append(' \u00a0|\u00a0 Aktualisiert: ' + new Date(r.updatedAt).toLocaleString('de-DE'));
        }

        body.appendChild(reviewText);
        body.appendChild(meta);

        div.appendChild(header);
        div.appendChild(body);

        return div;
    }

    // --- Fetch reviews ---
    async function fetchReviews() {
        const list = document.getElementById('reviews-list');
        const noReviews = document.getElementById('no-reviews');
        if (!list) return;

        let url = API_ENDPOINT;
        if (showingMyReviews) url += `?userId=${encodeURIComponent(currentUserId)}`;

        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error();
            const data = await res.json();
            list.innerHTML = '';

            if (!Array.isArray(data) || data.length === 0) {
                if (noReviews) { noReviews.classList.remove('hidden'); list.appendChild(noReviews); }
            } else {
                if (noReviews) noReviews.classList.add('hidden');
                data.forEach(r => list.appendChild(createReviewCard(r)));
            }
        } catch (e) {
            list.innerHTML = '<p class="text-red-500">Reviews konnten nicht geladen werden.</p>';
        }
    }

    // --- Create form submit ---
    document.getElementById('review-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const title = document.getElementById('movie-title').value.trim();
        const text = document.getElementById('review-text').value.trim();
        const stars = parseInt(document.getElementById('star-input').value);

        if (!title || !text || stars < 1 || stars > 5) {
            showToast('Bitte alle Felder ausfüllen und Sterne auswählen.', true);
            return;
        }

        const btn = document.getElementById('submit-button');
        btn.disabled = true;
        btn.textContent = 'Wird gespeichert...';

        try {
            const res = await fetch(API_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ appId, title, reviewText: text, stars })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'Speichern fehlgeschlagen');
            }
            showToast('Review erstellt!');
            document.getElementById('review-form').reset();
            document.getElementById('star-input').value = '0';
            setupStarRating('star-rating', 'star-input');
            fetchReviews();
        } catch (err) {
            showToast(err.message || 'Fehler beim Speichern.', true);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Review speichern';
        }
    });

    // --- Edit Modal ---
    function openEditModal(r) {
        document.getElementById('edit-review-id').value = r.id;
        document.getElementById('edit-movie-title').value = r.title;
        document.getElementById('edit-review-text').value = r.reviewText;
        document.getElementById('edit-star-input').value = r.stars;
        setupStarRating('edit-star-rating', 'edit-star-input');
        document.getElementById('edit-modal').classList.remove('hidden');
    }

    function closeEditModal() {
        document.getElementById('edit-modal').classList.add('hidden');
        document.getElementById('edit-form').reset();
        document.getElementById('edit-star-input').value = '0';
    }

    document.getElementById('edit-modal-close').addEventListener('click', closeEditModal);
    document.getElementById('edit-cancel-button').addEventListener('click', closeEditModal);
    document.getElementById('edit-modal').addEventListener('click', (e) => {
        if (e.target === document.getElementById('edit-modal')) closeEditModal();
    });

    document.getElementById('edit-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const reviewId = document.getElementById('edit-review-id').value;
        const title = document.getElementById('edit-movie-title').value.trim();
        const text = document.getElementById('edit-review-text').value.trim();
        const stars = parseInt(document.getElementById('edit-star-input').value);

        if (!title || !text || stars < 1 || stars > 5) {
            showToast('Bitte alle Felder ausfüllen und Sterne auswählen.', true);
            return;
        }

        const btn = document.getElementById('edit-submit-button');
        btn.disabled = true;
        btn.textContent = 'Aktualisiere...';

        try {
            const res = await fetch(`${API_ENDPOINT}/${reviewId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, reviewText: text, stars })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'Aktualisierung fehlgeschlagen');
            }
            showToast('Review aktualisiert!');
            closeEditModal();
            fetchReviews();
        } catch (err) {
            showToast(err.message || 'Fehler beim Aktualisieren.', true);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Änderungen speichern';
        }
    });

    // --- Filter toggle ---
    document.getElementById('filter-toggle').addEventListener('click', () => {
        showingMyReviews = !showingMyReviews;
        document.getElementById('filter-toggle').textContent = showingMyReviews ? 'Alle Reviews' : 'Meine Reviews';
        document.getElementById('reviews-heading').textContent = showingMyReviews ? 'Meine Reviews' : 'Alle Reviews';
        fetchReviews();
    });

    // --- Logout ---
    document.getElementById('logout-button').addEventListener('click', () => {
        window.location.href = '/logout';
    });

    // --- Init ---
    setupStarRating('star-rating', 'star-input');
    fetchReviews();
});
