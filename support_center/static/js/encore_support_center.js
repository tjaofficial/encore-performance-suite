(() => {
    "use strict";

    const input = document.getElementById("support-live-search");
    const results = document.getElementById("support-live-results");
    const status = document.getElementById("support-search-status");
    const source = document.getElementById("support-search-index");
    const page = document.querySelector("[data-support-center]");
    const backToTop = document.querySelector("[data-support-back-to-top]");

    let index = [];
    let activeResultIndex = -1;

    if (source) {
        try {
            index = JSON.parse(source.textContent || "[]");
        } catch (error) {
            console.warn("Encore Support search index could not be read.", error);
        }
    }

    const escapeHtml = (value) => String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

    const normalize = (value) => String(value || "").toLowerCase().trim();

    const scoreArticle = (article, terms) => {
        const title = normalize(article.title);
        const summary = normalize(article.summary);
        const category = normalize(article.category);
        const keywords = (article.keywords || []).map(normalize);
        let score = 0;
        let matchedTerms = 0;

        for (const term of terms) {
            let matched = false;
            if (title === term) { score += 18; matched = true; }
            else if (title.startsWith(term)) { score += 12; matched = true; }
            else if (title.includes(term)) { score += 9; matched = true; }
            if (keywords.some((keyword) => keyword === term)) { score += 8; matched = true; }
            else if (keywords.some((keyword) => keyword.includes(term))) { score += 5; matched = true; }
            if (summary.includes(term)) { score += 3; matched = true; }
            if (category.includes(term)) { score += 2; matched = true; }
            if (matched) matchedTerms += 1;
        }

        if (matchedTerms === terms.length && terms.length > 1) score += 8;
        return score;
    };

    const resultNodes = () => Array.from(results?.querySelectorAll(".support-live-result") || []);

    const setActiveResult = (nextIndex) => {
        const nodes = resultNodes();
        if (!nodes.length) return;
        activeResultIndex = Math.max(0, Math.min(nextIndex, nodes.length - 1));
        nodes.forEach((node, indexValue) => {
            node.classList.toggle("is-active", indexValue === activeResultIndex);
            node.setAttribute("aria-selected", indexValue === activeResultIndex ? "true" : "false");
        });
        nodes[activeResultIndex]?.scrollIntoView({ block: "nearest" });
    };

    const closeResults = () => {
        if (!results || !input) return;
        results.hidden = true;
        input.setAttribute("aria-expanded", "false");
        activeResultIndex = -1;
    };

    const render = () => {
        if (!input || !results || !status) return;
        const query = normalize(input.value);
        activeResultIndex = -1;

        if (!query) {
            closeResults();
            results.innerHTML = "";
            status.textContent = `Start typing to search all ${index.length} help articles.`;
            return;
        }

        const terms = query.split(/\s+/).filter(Boolean);
        const matches = index
            .map((article) => ({ article, score: scoreArticle(article, terms) }))
            .filter((row) => row.score > 0)
            .sort((a, b) => b.score - a.score || a.article.title.localeCompare(b.article.title))
            .slice(0, 12);

        status.textContent = matches.length
            ? `${matches.length} best match${matches.length === 1 ? "" : "es"} for “${input.value.trim()}”. Use ↑ ↓ and Enter to navigate.`
            : `No help articles matched “${input.value.trim()}”.`;

        results.innerHTML = matches.length
            ? matches.map(({ article }) => `
                <a class="support-live-result" role="option" aria-selected="false" href="${escapeHtml(article.url)}">
                    <div>
                        <span>${escapeHtml(article.category)}</span>
                        <strong>${escapeHtml(article.title)}</strong>
                        <p>${escapeHtml(article.summary)}</p>
                    </div>
                    <b aria-hidden="true">→</b>
                </a>
            `).join("")
            : `<div class="support-no-results">Try a shorter phrase such as <strong>teacher login</strong>, <strong>payments</strong>, <strong>import</strong>, or <strong>attendance</strong>.</div>`;

        results.hidden = false;
        input.setAttribute("aria-expanded", "true");
    };

    input?.addEventListener("input", render);
    input?.addEventListener("focus", () => {
        if (input.value.trim()) render();
    });
    input?.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
            event.preventDefault();
            if (results?.hidden) render();
            setActiveResult(activeResultIndex + 1);
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActiveResult(activeResultIndex <= 0 ? resultNodes().length - 1 : activeResultIndex - 1);
        } else if (event.key === "Enter" && activeResultIndex >= 0) {
            event.preventDefault();
            resultNodes()[activeResultIndex]?.click();
        } else if (event.key === "Escape") {
            closeResults();
            input.blur();
        }
    });

    document.addEventListener("keydown", (event) => {
        const shortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
        if (!shortcut || !input) return;
        event.preventDefault();
        input.focus();
        input.select();
        render();
    });

    document.addEventListener("click", (event) => {
        if (!results || !input) return;
        if (!event.target.closest(".support-search-shell")) closeResults();
    });

    document.querySelectorAll("[data-support-category-toggle]").forEach((button) => {
        button.addEventListener("click", () => {
            const key = button.dataset.supportCategoryToggle;
            const panel = document.querySelector(`[data-support-category-more="${key}"]`);
            if (!panel) return;
            const expanding = panel.hidden;
            panel.hidden = !expanding;
            button.setAttribute("aria-expanded", expanding ? "true" : "false");
            button.textContent = expanding ? "Show fewer articles" : `Show all ${button.dataset.count} articles`;
        });
    });

    document.querySelectorAll("[data-support-category-collapse]").forEach((button) => {
        button.addEventListener("click", () => {
            const key = button.dataset.supportCategoryCollapse;
            const body = document.querySelector(`[data-support-category-body="${key}"]`);
            if (!body) return;
            const expanding = body.hidden;
            body.hidden = !expanding;
            button.setAttribute("aria-expanded", expanding ? "true" : "false");
            button.setAttribute("aria-label", `${expanding ? "Collapse" : "Expand"} category`);
        });
    });

    const expandAllButton = document.querySelector("[data-support-expand-all]");
    expandAllButton?.addEventListener("click", () => {
        const bodies = Array.from(document.querySelectorAll("[data-support-category-body]"));
        const shouldExpand = bodies.some((body) => body.hidden);
        bodies.forEach((body) => { body.hidden = !shouldExpand; });
        document.querySelectorAll("[data-support-category-collapse]").forEach((button) => {
            button.setAttribute("aria-expanded", shouldExpand ? "true" : "false");
        });
        expandAllButton.textContent = shouldExpand ? "Collapse all categories" : "Expand all categories";
    });

    const topicToggle = document.querySelector("[data-topic-nav-toggle]");
    const topicList = document.querySelector("[data-topic-nav-list]");
    topicToggle?.addEventListener("click", () => {
        if (!topicList) return;
        const willShow = topicList.hidden;
        topicList.hidden = !willShow;
        topicToggle.setAttribute("aria-expanded", willShow ? "true" : "false");
        topicToggle.textContent = willShow ? "Hide topics" : "Show topics";
    });

    document.querySelectorAll("[data-support-topic-link]").forEach((link) => {
        link.addEventListener("click", () => {
            const key = link.dataset.supportTopicLink;
            const card = document.querySelector(`[data-support-category="${key}"]`);
            if (!card) return;
            document.querySelectorAll(".support-category-card.is-targeted").forEach((item) => item.classList.remove("is-targeted"));
            card.classList.add("is-targeted");
            window.setTimeout(() => card.classList.remove("is-targeted"), 1600);
        });
    });

    const sections = Array.from(document.querySelectorAll("[data-support-article-section]"));
    const sectionLinks = Array.from(document.querySelectorAll("[data-support-section-link]"));
    if (sections.length && sectionLinks.length && "IntersectionObserver" in window) {
        const observer = new IntersectionObserver((entries) => {
            const visible = entries
                .filter((entry) => entry.isIntersecting)
                .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
            if (!visible) return;
            sectionLinks.forEach((link) => {
                link.classList.toggle("is-active", link.dataset.supportSectionLink === visible.target.id);
            });
        }, { rootMargin: "-18% 0px -60% 0px", threshold: [0, .2, .5] });
        sections.forEach((section) => observer.observe(section));
    }

    const updateBackToTop = () => {
        if (!backToTop) return;
        backToTop.hidden = window.scrollY < 700;
    };
    window.addEventListener("scroll", updateBackToTop, { passive: true });
    updateBackToTop();
    backToTop?.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));

    if (page && window.location.hash?.startsWith("#category-")) {
        const target = document.querySelector(window.location.hash);
        target?.classList.add("is-targeted");
        window.setTimeout(() => target?.classList.remove("is-targeted"), 1600);
    }
})();
