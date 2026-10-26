/**
 * Snippet Otevírací doba (Odoo 20, Interaction).
 *
 * Stav obchůdku se načítá z /opening-hours/status každou minutu, rozvrh na 7 dní
 * z /opening-hours/schedule (při startu, při najetí myší a při kliknutí na lištu).
 *
 * Rozvrh se ukazuje po najetí myší (jen zařízení s myší) a kliknutím/klepnutím na lištu;
 * další klepnutí na lištu nebo na rozvrh ho zase schová (na mobilu dřív zůstal viset,
 * protože :hover po klepnutí trvá). Po schování kliknutím se na počítači neukáže,
 * dokud myš lištu neopustí.
 *
 * Odoo 20 zrušilo publicWidget (@web/legacy/js/public/public_widget), proto je to
 * Interaction. Při zastavení (vstup do editoru webu, uložení stránky) vrací obsah do
 * výchozího stavu šablony, takže editor do stránky neuloží vykreslený stav (v 19 se
 * tam ukládal a po načtení chvíli svítil starý).
 *
 * Třídy a struktura HTML jsou stejné jako v 19: snippet je uložený přímo ve stránkách
 * webu, šablona se při aktualizaci modulu nepřepisuje.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const POLL_INTERVAL = 60000; // 1 minuta

// stejné jako v šabloně s_opening_hours.xml
const SCHEDULE_LOADING_HTML =
    '<div class="text-center text-muted py-2">' +
    '<div class="spinner-border spinner-border-sm" role="status">' +
    '<span class="visually-hidden">Načítání...</span></div></div>';

async function fetchJson(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) {
        throw new Error(`${url}: HTTP ${response.status}`);
    }
    return response.json();
}

export class OpeningHours extends Interaction {
    // core Odoo má vlastní snippet website.s_opening_hours se stejnou třídou,
    // náš poznáme podle vnitřního .s_opening_hours_widget
    static selector = ".s_opening_hours";
    static selectorHas = ".s_opening_hours_widget";

    dynamicContent = {
        ".s_oh_status_bar": {
            "t-on-mouseenter": this.onBarMouseEnter,
            "t-on-click": this.onBarClick,
        },
        ".s_oh_schedule_tooltip": {
            "t-on-click": this.onTooltipClick,
        },
        _root: {
            "t-on-mouseleave": this.onMouseLeave,
        },
        _document: {
            "t-on-click": this.onDocumentClick,
        },
    };

    setup() {
        this.widgetEl = this.el.querySelector(".s_opening_hours_widget");
        this.tooltipEl = this.widgetEl.querySelector(".s_oh_schedule_tooltip");
    }

    start() {
        // obsah uložený editorem (starý stav) hned vyčistit
        this.resetContent();
        this.fetchStatus();
        this.fetchSchedule();
        this.setSafeInterval(() => this.fetchStatus(), POLL_INTERVAL);
    }

    destroy() {
        this.resetContent();
    }

    // -------------------------------------------------------------------------
    // Handlers
    // -------------------------------------------------------------------------

    onBarMouseEnter() {
        this.fetchSchedule();
    }

    onBarClick(ev) {
        if (!this.tooltipEl) {
            return;
        }
        ev.stopPropagation();
        if (this.isTooltipShown()) {
            this.hideTooltip();
        } else {
            this.widgetEl.classList.remove("s_oh_tooltip_closed");
            this.tooltipEl.classList.add("s_oh_tooltip_open");
            this.fetchSchedule();
        }
    }

    onTooltipClick(ev) {
        ev.stopPropagation();
        this.hideTooltip();
    }

    onMouseLeave() {
        this.widgetEl.classList.remove("s_oh_tooltip_closed");
    }

    onDocumentClick() {
        this.tooltipEl?.classList.remove("s_oh_tooltip_open");
    }

    /** Rozvrh je vidět: otevřený kliknutím, nebo najetím myší (jen zařízení s myší). */
    isTooltipShown() {
        if (this.tooltipEl.classList.contains("s_oh_tooltip_open")) {
            return true;
        }
        return (
            window.matchMedia("(hover: hover)").matches &&
            !this.widgetEl.classList.contains("s_oh_tooltip_closed") &&
            this.widgetEl.matches(":hover")
        );
    }

    hideTooltip() {
        this.tooltipEl.classList.remove("s_oh_tooltip_open");
        // na počítači by ho :hover hned ukázal znovu, do odjetí myší ho potlačit
        this.widgetEl.classList.add("s_oh_tooltip_closed");
    }

    // -------------------------------------------------------------------------
    // Data
    // -------------------------------------------------------------------------

    async fetchStatus() {
        let data;
        try {
            data = await this.waitFor(fetchJson("/opening-hours/status"));
        } catch {
            if (!this.isDestroyed) {
                this.protectSyncAfterAsync(() => {
                    const statusText = this.widgetEl.querySelector(".s_oh_status_text");
                    if (statusText) {
                        statusText.textContent = "Nedostupné";
                    }
                })();
            }
            return;
        }
        this.protectSyncAfterAsync(() => this.renderStatus(data))();
    }

    async fetchSchedule() {
        let schedule;
        try {
            schedule = await this.waitFor(fetchJson("/opening-hours/schedule"));
        } catch {
            if (!this.isDestroyed) {
                this.protectSyncAfterAsync(() => {
                    const list = this.widgetEl.querySelector(".s_oh_schedule_list");
                    if (list) {
                        list.innerHTML =
                            '<div class="text-center text-muted py-2">Nepodařilo se načíst</div>';
                    }
                })();
            }
            return;
        }
        this.protectSyncAfterAsync(() => this.renderSchedule(schedule))();
    }

    // -------------------------------------------------------------------------
    // DOM
    // -------------------------------------------------------------------------

    /** Vrátí dynamické části do stavu šablony s_opening_hours.xml. */
    resetContent() {
        const widget = this.widgetEl;
        const dot = widget.querySelector(".s_oh_dot");
        if (dot) {
            dot.className = "s_oh_dot s_oh_dot--loading";
        }
        const statusText = widget.querySelector(".s_oh_status_text");
        if (statusText) {
            statusText.textContent = "";
        }
        const todayHours = widget.querySelector(".s_oh_today_hours");
        if (todayHours) {
            todayHours.className = "s_oh_today_hours";
            todayHours.textContent = "";
        }
        const messageEl = widget.querySelector(".s_oh_message");
        if (messageEl) {
            messageEl.className = "s_oh_message";
            messageEl.textContent = "";
        }
        this.tooltipEl?.classList.remove("s_oh_tooltip_open");
        widget.classList.remove("s_oh_tooltip_closed");
        const list = widget.querySelector(".s_oh_schedule_list");
        if (list) {
            list.innerHTML = SCHEDULE_LOADING_HTML;
        }
    }

    renderStatus(data) {
        const widget = this.widgetEl;
        const dot = widget.querySelector(".s_oh_dot");
        const statusText = widget.querySelector(".s_oh_status_text");
        const todayHours = widget.querySelector(".s_oh_today_hours");
        const messageEl = widget.querySelector(".s_oh_message");
        if (!dot || !statusText || !todayHours || !messageEl) {
            return;
        }

        dot.className = "s_oh_dot";
        messageEl.className = "s_oh_message";
        messageEl.textContent = "";
        todayHours.textContent = "";
        todayHours.className = "s_oh_today_hours";

        const status = data.display_status;
        const today = data.today;

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

        // dnešní hodiny
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

    renderSchedule(schedule) {
        const list = this.widgetEl.querySelector(".s_oh_schedule_list");
        if (!list) {
            return;
        }
        list.replaceChildren();

        schedule.forEach((day, index) => {
            const row = document.createElement("div");
            row.className = "s_oh_schedule_row";
            if (index === 0) {
                row.classList.add("s_oh_schedule_row--today");
            }

            const nameEl = document.createElement("span");
            nameEl.className = "s_oh_schedule_day";
            nameEl.textContent = day.day_name;
            row.appendChild(nameEl);

            const hoursEl = document.createElement("span");
            hoursEl.className = "s_oh_schedule_hours";
            if (day.display_status === "closed_unexpected") {
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
                const reasonEl = document.createElement("span");
                reasonEl.className = "s_oh_schedule_reason";
                reasonEl.textContent = day.reason;
                row.appendChild(reasonEl);
            }

            list.appendChild(row);
        });
    }
}

/**
 * V editoru webu a v náhledu bloků (dialog „přidat blok“) běží taky, aby byl vidět
 * živý stav, ale bez klikání: klik v editoru vybírá blok. Vykreslené části nejsou
 * editovatelné; před uložením editor interakci zastaví a destroy() je vrátí do stavu
 * šablony.
 */
const OpeningHoursEdit = (I) =>
    class extends I {
        dynamicContent = {
            ".s_oh_status_bar, .s_oh_schedule_list": {
                "t-att-contenteditable": () => "false",
            },
        };
    };

registry.category("public.interactions").add("website_opening_hours.opening_hours", OpeningHours);

for (const mode of ["edit", "preview"]) {
    registry.category(`public.interactions.${mode}`).add("website_opening_hours.opening_hours", {
        Interaction: OpeningHours,
        mixin: OpeningHoursEdit,
    });
}
