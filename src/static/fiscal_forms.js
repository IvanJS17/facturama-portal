(function () {
    const GENERIC_RFC = "XAXX010101000";
    const RFC_ALLOWED = /[^A-Z0-9&Ñ]/g;
    const DIGITS_ONLY = /\D/g;

    function normalizeRfcInput(value) {
        return (value || "").toUpperCase().replace(RFC_ALLOWED, "").slice(0, 13);
    }

    function normalizeZipInput(value) {
        return (value || "").replace(DIGITS_ONLY, "").slice(0, 5);
    }

    function normalizeLegalNameInput(value) {
        return (value || "").toLocaleUpperCase("es-MX");
    }

    function parseIssuerZipMap() {
        const node = document.getElementById("issuer-zip-codes");
        if (!node) {
            return {};
        }
        try {
            return JSON.parse(node.textContent || "{}");
        } catch (error) {
            return {};
        }
    }

    function mountFiscalForm(form) {
        const rfcInput = form.querySelector("[data-fiscal-rfc]");
        const legalNameInput = form.querySelector("[data-fiscal-legal-name]");
        const zipInput = form.querySelector("[data-fiscal-zip]");
        const issuerInput = form.querySelector("#issuer_id");
        const taxRegimeInput = form.querySelector("#tax_regime");
        const cfdiUseInput = form.querySelector("#cfdi_use");
        const hintNode = form.querySelector("#generic-rfc-hint");
        const issuerZipMap = parseIssuerZipMap();

        if (rfcInput) {
            rfcInput.addEventListener("input", function () {
                this.value = normalizeRfcInput(this.value);
                applyGenericRfcDefaults();
            });
        }

        if (legalNameInput) {
            legalNameInput.addEventListener("input", function () {
                this.value = normalizeLegalNameInput(this.value);
            });
        }

        if (zipInput) {
            zipInput.addEventListener("input", function () {
                this.value = normalizeZipInput(this.value);
            });
        }

        if (issuerInput) {
            issuerInput.addEventListener("change", applyGenericRfcDefaults);
        }

        function applyGenericRfcDefaults() {
            if (!rfcInput || normalizeRfcInput(rfcInput.value) !== GENERIC_RFC) {
                if (hintNode) hintNode.textContent = "";
                return;
            }
            if (legalNameInput) legalNameInput.value = "PÚBLICO EN GENERAL";
            if (taxRegimeInput) taxRegimeInput.value = "616";
            if (cfdiUseInput) cfdiUseInput.value = "S01";

            const issuerId = issuerInput ? issuerInput.value : "";
            if (issuerId && issuerZipMap[issuerId]) {
                if (zipInput) zipInput.value = normalizeZipInput(issuerZipMap[issuerId]);
                if (hintNode) hintNode.textContent = "";
            } else if (hintNode) {
                hintNode.textContent = "Selecciona un emisor para completar el código postal del público en general.";
            }
        }

        applyGenericRfcDefaults();
    }

    document.querySelectorAll("form.client-fiscal-form, form.issuer-fiscal-form").forEach(mountFiscalForm);
})();
