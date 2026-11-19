
"use strict";

/**
 * MoneyTrack - Main JavaScript
 *
 * Shared interactions used across application pages.
 */

document.addEventListener("DOMContentLoaded", () => {
    initializeFlashMessages();
});


/**
 * Automatically hide flash messages after a few seconds.
 */
function initializeFlashMessages() {
    const messages = document.querySelectorAll(".flash-message");

    messages.forEach((message) => {
        window.setTimeout(() => {
            message.classList.add("flash-hidden");

            window.setTimeout(() => {
                message.remove();
            }, 300);
        }, 4000);
    });
}
