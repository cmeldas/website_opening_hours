/**
 * Opening Hours Website Snippet
 * Polls /opening-hours/status every 60 seconds.
 * Shows tooltip with 7-day schedule on hover.
 */
(function () {
    var POLL_INTERVAL = 60000; // 1 minute

    function updateStatus(widget, data) {
        var dot = widget.querySelector(".s_oh_dot");
        var statusText = widget.querySelector(".s_oh_status_text");
        var todayHours = widget.querySelector(".s_oh_today_hours");
        var messageEl = widget.querySelector(".s_oh_message");

        // Reset
        dot.className = "s_oh_dot";
        messageEl.className = "s_oh_message";
        messageEl.textContent = "";
        todayHours.textContent = "";
        todayHours.className = "s_oh_today_hours";

        var status = data.display_status;
        var today = data.today;

        if (status === "open") {
            dot.classList.add("s_oh_dot--open");
            statusText.textContent = "Otevřeno";
        } else if (status === "open_early") {
            dot.classList.add("s_oh_dot--open");
            statusText.textContent = "Otevřeno";
            messageEl.classList.add("s_oh_message--info");
            messageEl.textContent = data.message;
        } else if (status === "closed_unexpected") {
            dot.classList.add("s_oh_dot--closed");
            statusText.textContent = "Zavřeno";
            messageEl.classList.add("s_oh_message--warning");
            messageEl.textContent = data.message;
        } else {
            dot.classList.add("s_oh_dot--closed");
            statusText.textContent = "Zavřeno";
        }

        // Today's hours
        if (status === "closed_unexpected" && data.scheduled_hours) {
            todayHours.classList.add("s_oh_today_hours--expected");
            todayHours.textContent = "Plán: " + data.scheduled_hours;
        } else if (today.is_open) {
            todayHours.textContent = today.open_time + " – " + today.close_time;
        } else {
            todayHours.textContent = "Dnes zavřeno";
        }

        if (today.reason) {
            todayHours.textContent += " (" + today.reason + ")";
        }
    }

    function renderSchedule(widget, schedule) {
        var list = widget.querySelector(".s_oh_schedule_list");
        list.innerHTML = "";

        var today = new Date();
        today.setHours(0, 0, 0, 0);

        schedule.forEach(function (day, index) {
            var row = document.createElement("div");
            row.className = "s_oh_schedule_row";
            if (index === 0) {
                row.classList.add("s_oh_schedule_row--today");
            }

            var nameEl = document.createElement("span");
            nameEl.className = "s_oh_schedule_day";
            nameEl.textContent = day.day_name;
            row.appendChild(nameEl);

            var hoursEl = document.createElement("span");
            hoursEl.className = "s_oh_schedule_hours";

            if (day.display_status === "closed_unexpected") {
                // Scheduled open but HA says closed — show planned hours in orange
                hoursEl.textContent = day.open_time + " – " + day.close_time;
                hoursEl.classList.add("s_oh_schedule_hours--unexpected");
            } else if (day.is_open) {
                hoursEl.textContent = day.open_time + " – " + day.close_time;
                hoursEl.classList.add("s_oh_schedule_hours--open");
            } else {
                hoursEl.textContent = "Zavřeno";
                hoursEl.classList.add("s_oh_schedule_hours--closed");
            }
            row.appendChild(hoursEl);

            if (day.reason) {
                var reasonEl = document.createElement("span");
                reasonEl.className = "s_oh_schedule_reason";
                reasonEl.textContent = day.reason;
                row.appendChild(reasonEl);
            }

            list.appendChild(row);
        });
    }

    function fetchStatus(widget) {
        fetch("/opening-hours/status")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                updateStatus(widget, data);
            })
            .catch(function () {
                var statusText = widget.querySelector(".s_oh_status_text");
                if (statusText) statusText.textContent = "Nedostupné";
            });
    }

    function fetchSchedule(widget) {
        fetch("/opening-hours/schedule")
            .then(function (r) { return r.json(); })
            .then(function (data) { renderSchedule(widget, data); })
            .catch(function () {
                var list = widget.querySelector(".s_oh_schedule_list");
                if (list) list.innerHTML = '<div class="text-center text-muted py-2">Nepodařilo se načíst</div>';
            });
    }

    function initWidgets() {
        var widgets = document.querySelectorAll(".s_opening_hours");
        widgets.forEach(function (section) {
            var widget = section.querySelector(".s_opening_hours_widget");
            if (!widget) return;

            // Initial fetch
            fetchStatus(widget);
            fetchSchedule(widget);

            // Poll status every minute
            setInterval(function () {
                fetchStatus(widget);
            }, POLL_INTERVAL);

            // Refresh schedule on hover (in case day changed)
            var bar = widget.querySelector(".s_oh_status_bar");
            var tooltip = widget.querySelector(".s_oh_schedule_tooltip");
            if (bar) {
                bar.addEventListener("mouseenter", function () {
                    fetchSchedule(widget);
                });
                // Touch toggle for mobile
                bar.addEventListener("click", function (e) {
                    if (tooltip) {
                        e.stopPropagation();
                        var isOpen = tooltip.classList.toggle("s_oh_tooltip_open");
                        if (isOpen) fetchSchedule(widget);
                    }
                });
            }
            if (tooltip) {
                tooltip.addEventListener("click", function (e) {
                    e.stopPropagation();
                });
            }
            // Close tooltip on outside click
            document.addEventListener("click", function () {
                if (tooltip) tooltip.classList.remove("s_oh_tooltip_open");
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initWidgets);
    } else {
        initWidgets();
    }
})();
