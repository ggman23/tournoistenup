// ==UserScript==
// @name         TenUp Auto-Cookie Farmer (Local PC)
// @namespace    http://tampermonkey.net/
// @version      1.1
// @description  Maintient la session active et pousse les cookies vers cookie_server.py sur le PC local
// @author       Toi
// @match        https://tenup.fft.fr/*
// @match        https://tenup.queue-it.net/*
// @grant        GM_xmlhttpRequest
// ==/UserScript==

(function() {
    'use strict';

    var SERVER_URL   = "http://localhost:5057/update_cookie";
    var REFRESH_MS   = 8 * 60 * 1000;  // 8 minutes

    function sendCookies() {
        var cookies = document.cookie;
        if (!cookies) {
            console.log("[TenUp] Aucun cookie accessible (peut-être tous HttpOnly).");
            return;
        }

        console.log("[TenUp] Envoi de " + cookies.split(";").length + " cookie(s) vers cookie_server.py...");

        GM_xmlhttpRequest({
            method:  "POST",
            url:     SERVER_URL,
            data:    cookies,
            headers: { "Content-Type": "text/plain" },
            onload: function(r) {
                if (r.status === 200) {
                    console.log("%c[TenUp] ✅ Cookies mis à jour sur le PC !", "color:#00cc44;font-weight:bold");
                } else {
                    console.warn("[TenUp] Réponse inattendue :", r.status, r.responseText);
                }
            },
            onerror: function() {
                console.error("%c[TenUp] ❌ Impossible de joindre cookie_server.py — est-il bien lancé ?", "color:red;font-weight:bold");
            }
        });
    }

    // Envoi immédiat au chargement de la page
    sendCookies();

    // Rafraîchissement automatique toutes les 8 min pour garder la session vivante
    setTimeout(function() {
        console.log("[TenUp] Rafraîchissement de la page pour renouveler la session...");
        window.location.reload();
    }, REFRESH_MS);

})();
