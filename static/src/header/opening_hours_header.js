/**
 * Otevírací doba v hlavičce webu (šablona header_opening_hours, Odoo 20 Interaction).
 *
 * Server vykreslí předpokládanou dobu podle rozvrhu a rozvrh na 7 dní. Stav (tečka a
 * Otevřeno/Zavřeno) je skrytý, dokud ho nepotvrdí /opening-hours/status; pak se třídou
 * o_oh_known vysune zleva (CSS) a hodiny se posunou doprava. Starý stav tak nikdy
 * neproblikne. Stav se obnovuje každou minutu.
 *
 * Lišta je tlačítko: kliknutí/klepnutí rozbalí rozvrh, další klepnutí (i na rozvrh) ho
 * schová, Escape taky. Na zařízeních s myší se rozvrh ukáže i po najetí; po schování
 * kliknutím až do odjetí myší ne (na mobilu by :hover po klepnutí visel).
 *
 * Komponenta je na stránce dvakrát (v liště a pod ní, podle šířky je vidět jedna),
 * dotaz na stav sdílejí.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const POLL_INTERVAL = 60000; // 1 minuta
const SHARED_FETCH_MS = 5000;

const STATUS_TEXT = {
    open: "Otevřeno",
    open_early: "Otevřeno",
    closed_unexpected: "Zavřeno",
    closed: "Zavřeno",
};

let sharedFetch = null;

/** Stav obchůdku; obě kopie komponenty dostanou stejnou odpověď jedním dotazem. */
function fetchStatus() {
    if (!sharedFetch || Date.now() - sharedFetch.time > SHARED_FETCH_MS) {
        const promise = fetch("/opening-hours/status", { headers: { Accept: "application/json" } }).then(
            (response) => {
                if (!response.ok) {
                    throw new Error(`/opening-hours/status: HTTP ${response.status}`);
                }
                return response.json();
            }
        );
        sharedFetch = { time: Date.now(), promise };
    }
    return sharedFetch.promise;
}

export class OpeningHoursHeader extends Interaction {
    static selector = ".o_oh";

    dynamicContent = {
        _root: {
            "t-on-mouseleave": this.onMouseLeave,
            "t-att-class": () => ({
                o_oh_known: Boolean(this.status),
                o_oh_is_open: Boolean(this.status?.is_open),
                o_oh_unexpected: this.status?.display_status === "closed_unexpected",
                o_oh_expanded: this.isOpen,
                o_oh_hover_off: this.hoverSuppressed,
            }),
        },
        ".o_oh_bar": {
            "t-on-click": this.onBarClick,
            "t-on-keydown": this.onBarKeydown,
            "t-att-aria-expanded": () => String(this.isOpen),
        },
        ".o_oh_status_text": {
            "t-out": () => (this.status ? STATUS_TEXT[this.status.display_status] || "" : ""),
        },
        ".o_oh_message": {
            "t-out": () => this.status?.message || "",
        },
        ".o_oh_panel": {
            "t-on-click": this.onPanelClick,
        },
        _document: {
            "t-on-click": this.onDocumentClick,
        },
    };

    setup() {
        this.status = null;
        // rozbaleno kliknutím/klepnutím; najetí myší řeší CSS
        this.isOpen = false;
        // po schování kliknutím neukazovat po najetí myší, dokud myš neodjede
        this.hoverSuppressed = false;
    }

    start() {
        this.refreshStatus();
        this.setSafeInterval(() => this.refreshStatus(), POLL_INTERVAL);
    }

    async refreshStatus() {
        let status;
        try {
            status = await this.waitFor(fetchStatus());
        } catch {
            // bez spojení zůstane poslední potvrzený stav, nebo jen předpokládaná doba
            return;
        }
        // waitFor po vyřešení sám zavolá updateContent
        this.status = status;
    }

    // -------------------------------------------------------------------------
    // Handlers
    // -------------------------------------------------------------------------

    onBarClick(ev) {
        ev.stopPropagation();
        if (this.isPanelShown()) {
            this.hidePanel();
        } else {
            this.isOpen = true;
            this.hoverSuppressed = false;
        }
    }

    onBarKeydown(ev) {
        if (ev.key === "Escape" && this.isPanelShown()) {
            this.hidePanel();
        }
    }

    onPanelClick(ev) {
        ev.stopPropagation();
        this.hidePanel();
    }

    onMouseLeave() {
        this.hoverSuppressed = false;
    }

    onDocumentClick() {
        this.isOpen = false;
    }

    /** Rozvrh je vidět: rozbalený kliknutím, nebo najetím myší (jen zařízení s myší). */
    isPanelShown() {
        if (this.isOpen) {
            return true;
        }
        return (
            window.matchMedia("(hover: hover)").matches && !this.hoverSuppressed && this.el.matches(":hover")
        );
    }

    hidePanel() {
        this.isOpen = false;
        // na počítači by ho :hover hned ukázal znovu, do odjetí myší ho potlačit
        this.hoverSuppressed = true;
    }
}

registry.category("public.interactions").add("website_opening_hours.header", OpeningHoursHeader);
