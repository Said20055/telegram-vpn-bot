// webapp/static/js/scripts.js

// ============================================================
// Toast System
// ============================================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast-item ${type}`;
    toast.innerHTML = `<span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============================================================
// State
// ============================================================

let activePromo = null;

// ============================================================
// Payment
// ============================================================

async function initPayment(tariffName, price, btn) {
    if (!btn) return;
    btn.classList.add('btn-loading');

    try {
        const payload = { tariff_name: tariffName, price: price };
        if (activePromo) {
            payload.promo_code = activePromo.code;
            payload.discount_percent = activePromo.discount_percent;
        }

        const response = await fetch('/payment/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            const data = await response.json();
            window.location.href = data.payment_url;
        } else if (response.status === 401) {
            window.location.href = '/login';
        } else if (response.status === 409) {
            showToast("У вас уже есть неоплаченный счёт. Дождитесь отмены (30 мин) или завершите оплату.", "warning");
        } else {
            showToast("Ошибка при создании платежа. Попробуйте позже.", "error");
        }
    } catch (error) {
        console.error('Payment error:', error);
        showToast("Ошибка соединения с сервером.", "error");
    } finally {
        btn.classList.remove('btn-loading');
    }
}

// ============================================================
// Promo Code
// ============================================================

async function applyPromo() {
    const input = document.getElementById('promoInput');
    const resultDiv = document.getElementById('promoResult');
    const code = input.value.trim();

    if (!code) {
        resultDiv.innerHTML = '<span class="text-danger-custom">Введите промокод</span>';
        return;
    }

    resultDiv.innerHTML = '<span class="text-gray">Проверяю...</span>';

    try {
        const response = await fetch('/payment/validate-promo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code })
        });

        const data = await response.json();

        if (data.valid) {
            if (data.type === 'discount') {
                activePromo = { code: data.code, discount_percent: data.discount_percent };
                resultDiv.innerHTML = `<span class="text-success-custom">Скидка ${data.discount_percent}% применена!</span>`;
                showToast(`Промокод применён: скидка ${data.discount_percent}%`, 'success');
                updateTariffPrices(data.discount_percent);
            } else if (data.type === 'bonus_days') {
                resultDiv.innerHTML = '<span class="text-gray">Применяю бонусные дни...</span>';
                const applyResp = await fetch('/payment/apply-bonus-promo', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: code })
                });
                if (applyResp.ok) {
                    const applyData = await applyResp.json();
                    resultDiv.innerHTML = `<span class="text-success-custom">Начислено ${applyData.bonus_days} бонусных дней!</span>`;
                    showToast(`+${applyData.bonus_days} бонусных дней!`, 'success');
                    setTimeout(() => location.reload(), 2000);
                } else {
                    resultDiv.innerHTML = '<span class="text-danger-custom">Ошибка при применении промокода</span>';
                }
            }
        } else {
            activePromo = null;
            resultDiv.innerHTML = `<span class="text-danger-custom">${data.error}</span>`;
            resetTariffPrices();
        }
    } catch (error) {
        console.error('Promo error:', error);
        resultDiv.innerHTML = '<span class="text-danger-custom">Ошибка соединения</span>';
    }
}

function updateTariffPrices(discountPercent) {
    document.querySelectorAll('.tariff-price').forEach(el => {
        const originalPrice = parseInt(el.dataset.originalPrice || el.textContent);
        if (!el.dataset.originalPrice) {
            el.dataset.originalPrice = originalPrice;
        }
        const newPrice = Math.round(originalPrice * (1 - discountPercent / 100));
        el.innerHTML = `<s class="text-gray" style="font-size:0.6em">${originalPrice} ₽</s> ${newPrice} <small class="fs-6">₽</small>`;
    });
}

function resetTariffPrices() {
    document.querySelectorAll('.tariff-price').forEach(el => {
        if (el.dataset.originalPrice) {
            el.innerHTML = `${el.dataset.originalPrice} <small class="fs-6">₽</small>`;
        }
    });
}

// ============================================================
// Copy Functions
// ============================================================

function copyLink() {
    const input = document.getElementById("subLink");
    if (!input) return;
    navigator.clipboard.writeText(input.value).then(() => {
        showToast("Ключ скопирован!", "success");
    });
}

function initRefLink() {
    const input = document.getElementById("refLink");
    if (!input) return;
    const ref = input.dataset.ref;
    if (ref) input.value = window.location.origin + "/register?ref=" + ref;
}

function copyRefLink() {
    const input = document.getElementById("refLink");
    if (!input) return;
    navigator.clipboard.writeText(input.value).then(() => {
        showToast("Реферальная ссылка скопирована!", "success");
    });
}

// ============================================================
// OS Detection
// ============================================================

function detectOSAndSetLink() {
    const userAgent = navigator.userAgent || navigator.vendor || window.opera;
    const downloadBtn = document.getElementById("downloadBtn");
    const appDesc = document.getElementById("appDescription");
    const osIcon = document.getElementById("osIcon");
    const btnTextEl = document.getElementById("btnText");

    if (!downloadBtn) return;

    if (/android/i.test(userAgent)) {
        downloadBtn.href = "https://play.google.com/store/apps/details?id=com.happproxy.app";
        appDesc.textContent = "Для Android рекомендуем Happ.";
        osIcon.className = "fab fa-android me-1";
        btnTextEl.textContent = "Google Play";
    } else if (/iPad|iPhone|iPod/.test(userAgent) && !window.MSStream) {
        downloadBtn.href = "https://apps.apple.com/app/happ-proxy-utility/id6504287215";
        appDesc.textContent = "Для iOS рекомендуем Happ.";
        osIcon.className = "fab fa-app-store-ios me-1";
        btnTextEl.textContent = "App Store";
    } else if (/Win/i.test(userAgent)) {
        downloadBtn.href = "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe";
        appDesc.textContent = "Для Windows рекомендуем Happ.";
        osIcon.className = "fab fa-windows me-1";
        btnTextEl.textContent = "Скачать для Windows";
    } else if (/Mac/i.test(userAgent)) {
        downloadBtn.href = "https://apps.apple.com/app/happ-proxy-utility/id6504287215";
        appDesc.textContent = "Для macOS рекомендуем Happ.";
        osIcon.className = "fab fa-apple me-1";
        btnTextEl.textContent = "Скачать для macOS";
    } else {
        downloadBtn.href = "https://play.google.com/store/apps/details?id=com.happproxy.app";
        appDesc.textContent = "Выберите приложение для вашей ОС.";
        osIcon.className = "fas fa-download me-1";
        btnTextEl.textContent = "Скачать";
    }
}

// ============================================================
// Password Strength Indicator
// ============================================================

function initPasswordStrength() {
    const passwordInput = document.getElementById('registerPassword');
    const strengthBar = document.getElementById('passwordStrengthBar');
    if (!passwordInput || !strengthBar) return;

    passwordInput.addEventListener('input', function() {
        const val = this.value;
        strengthBar.className = 'bar';

        if (val.length === 0) {
            strengthBar.style.width = '0';
            return;
        }
        if (val.length < 6) {
            strengthBar.classList.add('weak');
        } else if (val.length < 10 || !/[A-Z]/.test(val) || !/[0-9]/.test(val)) {
            strengthBar.classList.add('medium');
        } else {
            strengthBar.classList.add('strong');
        }
    });
}

// ============================================================
// Form Loading State
// ============================================================

function initFormLoading() {
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function() {
            const btn = form.querySelector('button[type="submit"]');
            if (btn && !btn.classList.contains('btn-link')) {
                btn.classList.add('btn-loading');
            }
        });
    });
}

// ============================================================
// Scroll Animations (IntersectionObserver)
// ============================================================

function initScrollAnimations() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.animationPlayState = 'running';
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.animate-in').forEach(el => {
        el.style.animationPlayState = 'paused';
        observer.observe(el);
    });
}

// ============================================================
// Init
// ============================================================

document.addEventListener("DOMContentLoaded", function() {
    detectOSAndSetLink();
    initRefLink();
    initPasswordStrength();
    initFormLoading();
    initScrollAnimations();
});
