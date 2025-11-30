// webapp/static/js/scripts.js

async function initPayment(tariffName, price) {
    const btn = event.target; // Кнопка, на которую нажали
    const originalText = btn.innerHTML;
    
    // 1. Меняем кнопку на "Загрузка..."
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
    btn.disabled = true;

    try {
        // 2. Отправляем запрос на бэкенд
        const response = await fetch('/payment/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                tariff_name: tariffName,
                price: price
            })
        });

        if (response.ok) {
            const data = await response.json();
            // 3. Если все ок, переходим на ЮКассу
            window.location.href = data.payment_url;
        } else {
            // Если ошибка (например, не залогинен)
            if (response.status === 401) {
                window.location.href = '/login';
            } else {
                alert("Ошибка при создании платежа. Попробуйте позже.");
            }
        }
    } catch (error) {
        console.error('Payment error:', error);
        alert("Ошибка соединения с сервером.");
    } finally {
        // Возвращаем кнопку в исходное состояние (если редирект не случился)
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// Функция копирования (оставляем как была)
function copyLink() {
    var copyText = document.getElementById("subLink");
    if (!copyText) return;
    copyText.select();
    copyText.setSelectionRange(0, 99999);
    navigator.clipboard.writeText(copyText.value).then(function() {
        const btn = document.getElementById("copyBtn");
        btn.classList.replace("btn-outline-secondary", "btn-success");
        setTimeout(() => {
            btn.classList.replace("btn-success", "btn-outline-secondary");
        }, 2000);
    });
}


document.addEventListener("DOMContentLoaded", function() {
    detectOSAndSetLink();
});

function detectOSAndSetLink() {
    const userAgent = navigator.userAgent || navigator.vendor || window.opera;
    const downloadBtn = document.getElementById("downloadBtn");
    const appDesc = document.getElementById("appDescription");
    const osIcon = document.getElementById("osIcon");
    const btnText = document.getElementById("btnText");

    if (!downloadBtn) return; // Если элемента нет на странице (например, нет подписки)

    // Ссылки на приложения
    // Android: V2RayTun (как в боте)
    // iOS: Streisand или V2Box (V2RayTun нет в AppStore)
    // Windows: Hiddify (лучший клиент сейчас)
    
    if (/android/i.test(userAgent)) {
        downloadBtn.href = "https://play.google.com/store/apps/details?id=com.v2raytun.android";
        appDesc.innerText = "Для Android рекомендуем V2RayTun.";
        osIcon.className = "fab fa-android";
        btnText.innerText = "Скачать из Google Play";
    } 
    else if (/iPad|iPhone|iPod/.test(userAgent) && !window.MSStream) {
        downloadBtn.href = "https://apps.apple.com/us/app/v2raytun/id6476628951";
        appDesc.innerText = "Для iOS рекомендуем V2RayTun.";
        osIcon.className = "fab fa-app-store-ios";
        btnText.innerText = "Скачать из App Store";
    } 
    else if (/Win/i.test(userAgent)) {
        downloadBtn.href = "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe";
        appDesc.innerText = "Для Windows рекомендуем Happ.";
        osIcon.className = "fab fa-windows";
        btnText.innerText = "Скачать для Windows";
    } 
    else if (/Mac/i.test(userAgent)) {
        downloadBtn.href = "https://apps.apple.com/us/app/v2raytun/id6476628951";
        appDesc.innerText = "Для macOS рекомендуем V2RayTun.";
        osIcon.className = "fab fa-apple";
        btnText.innerText = "Скачать для macOS";
    } 
    else {
        // Дефолт (если не определили)
        downloadBtn.href = "https://play.google.com/store/apps/details?id=com.v2raytun.android";
        appDesc.innerText = "Выберите приложение для вашей ОС.";
        osIcon.className = "fas fa-download";
        btnText.innerText = "Скачать приложение";
    }
}



  document.addEventListener("DOMContentLoaded", function() {
        const form = document.getElementById('resetForm');
        const btn = document.getElementById('submitBtn');
        const btnText = document.getElementById('btnText');
        const btnIcon = document.getElementById('btnIcon');

        if(form) {
            form.addEventListener('submit', function() {
                // 1. Блокируем кнопку, чтобы не нажали дважды
                btn.disabled = true;
                
                // 2. Меняем текст
                btnText.innerText = "Отправляем...";
                
                // 3. Меняем иконку самолетика на спиннер (крутилку)
                btnIcon.className = "spinner-border spinner-border-sm ms-2";
                btnIcon.setAttribute("role", "status");
                btnIcon.setAttribute("aria-hidden", "true");
            });
        }
    });