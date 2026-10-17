window.__ModuleLoader__.load({
	id: "dsh-balanced-search",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

		const react = require("react");
		const primitives = require("@deepseek-ai/dsh-client-ui-primitives");
		const {
			DisclosureRow,
			TextShimmer,
			WebBlock,
			IconGlobeOutlineRegular,
			IconBrowseOutlineRegular
		} = primitives;

		//#region locale
		/**
		 * This package ships no locale JSON and therefore registers no locale
		 * namespace: `t` is only bound for registrations that declare one, so the
		 * view carries its own two-language table and detects the shell language.
		 */
		const COPY = {
			zh: {
				searchTitle: "网页搜索",
				fetchTitle: "网页获取",
				badge: "balanced",
				searching: "正在搜索网页",
				fetching: "正在获取网页",
				searchingCount: (n) => `正在搜索 ${String(n)} 个查询`,
				found: (n) => `找到 ${String(n)} 条结果`,
				noResults: "未找到结果",
				sourcesTruncated: "来源列表已截断",
				contentTruncated: "内容已截断",
				http: "HTTP",
				provider: "提供方",
				elapsed: "耗时",
				results: (n) => `${String(n)} 条结果`,
				query: "查询词",
				url: "网址",
				length: "正文长度",
				failedPrefix: "失败",
				inspect: "在轨迹中查看"
			},
			en: {
				searchTitle: "Search",
				fetchTitle: "Fetch",
				badge: "balanced",
				searching: "Searching the web",
				fetching: "Fetching page",
				searchingCount: (n) => `Searching ${String(n)} queries`,
				found: (n) => `Found ${String(n)} results`,
				noResults: "No results found",
				sourcesTruncated: "Source list truncated",
				contentTruncated: "Content truncated",
				http: "HTTP",
				provider: "Provider",
				elapsed: "Elapsed",
				results: (n) => `${String(n)} results`,
				query: "Query",
				url: "URL",
				length: "Content length",
				failedPrefix: "Failed",
				inspect: "Inspect"
			}
		};
		/** Detect the shell language once; the Web GUI sets `<html lang>` from the locale plugin. */
		function detectLanguage() {
			try {
				if (typeof document !== "undefined") {
					const declared = document.documentElement?.lang;
					if (typeof declared === "string" && declared !== "") return declared;
				}
				if (typeof navigator !== "undefined") {
					const nav = navigator.language ?? navigator.languages?.[0];
					if (typeof nav === "string" && nav !== "") return nav;
				}
			} catch {}
			return "en";
		}
		const LANGUAGE = detectLanguage();
		const copy = /^zh/i.test(LANGUAGE) ? COPY.zh : COPY.en;
		//#endregion

		//#region models
		/** First line of a possibly multi-line string, mirroring the official row summary rule. */
		function firstLine(text) {
			const nl = text.indexOf("\n");
			return nl === -1 ? text : text.slice(0, nl);
		}
		/** Parse recorded argument text; returns undefined for absent or malformed JSON. */
		function parseArgs(raw) {
			if (typeof raw !== "string" || raw === "") return void 0;
			try {
				return JSON.parse(raw);
			} catch {
				return void 0;
			}
		}
		/**
		 * Read the model arguments at whichever stage the call is in. A result node
		 * exposes `call.argsRaw` (null when the paired call left the loaded window) and
		 * a `PartialArguments` view under `args`; a started call exposes `argsRaw`; a
		 * preparing call exposes only the streaming `args` view.
		 * @returns a plain object of top-level fields, or null.
		 */
		function readArgs(block) {
			if (block === null || typeof block !== "object") return null;
			if ("kind" in block) {
				const parsed = parseArgs(block.call?.argsRaw);
				if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
				if (block.args !== void 0 && block.args !== null && typeof block.args === "object") return block.args;
				return null;
			}
			const parsed = parseArgs(block.argsRaw);
			if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
			if (block.args !== void 0 && block.args !== null && typeof block.args === "object") return block.args;
			return null;
		}
		/** Read one string field from an argument view, tolerating a plain object or a PartialArguments face. */
		function readString(args, key) {
			if (args === null) return void 0;
			const value = args[key];
			return typeof value === "string" && value !== "" ? value : void 0;
		}
		/** Read the query list: `queries[]`, else a single `query`, then `q`. */
		function readQueries(args) {
			if (args === null) return [];
			const list = args.queries;
			if (Array.isArray(list)) {
				const kept = [];
				for (const value of list) if (typeof value === "string" && value.trim() !== "") kept.push(value);
				if (kept.length > 0) return kept;
			}
			const single = readString(args, "query") ?? readString(args, "q");
			return single === void 0 ? [] : [single];
		}
		/** Whether a settled result carries a non-empty single text block. */
		function resultText(block) {
			if (block === null || typeof block !== "object" || !("kind" in block)) return null;
			if (!Array.isArray(block.content) || block.content.length !== 1) return null;
			const only = block.content[0];
			return only !== void 0 && only !== null && only.type === "text" && typeof only.text === "string" ? only.text : null;
		}
		/** Narrow recorded sources; returns null when the shape is not the persisted web-card layout. */
		function readSources(value) {
			if (!Array.isArray(value)) return null;
			const sources = [];
			for (const source of value) {
				if (typeof source !== "object" || source === null || Array.isArray(source)) return null;
				const { url, title, snippet } = source;
				if (typeof url !== "string") return null;
				sources.push({
					url,
					...typeof title === "string" ? { title } : {},
					...typeof snippet === "string" ? { snippet } : {}
				});
			}
			return sources;
		}
		/** One row state, mirroring the official Tool row vocabulary. */
		function readState(block) {
			if (block === null || typeof block !== "object") return "ok";
			if (!("kind" in block)) return block.phase === "preparing" ? "preparing" : "running";
			if (block.error?.code === "interrupted") return "stopped";
			return block.isError ? "error" : "ok";
		}
		/**
		 * Build the WebBlock body and the metadata line from the persisted
		 * `presentationMeta` (`balanced: true`), degrading to the recorded result
		 * text when the meta is absent, for example in sessions written before the
		 * meta existed. Never throws.
		 */
		function readWeb(block, queries) {
			const state = readState(block);
			const settled = block !== null && typeof block === "object" && "kind" in block;
			const meta = settled && typeof block.meta === "object" && block.meta !== null && !Array.isArray(block.meta) ? block.meta : null;
			const metaKind = meta !== null && (meta.kind === "search" || meta.kind === "fetch") ? meta.kind : null;
			const kind = metaKind ?? (queries.length > 0 ? "search" : "fetch");
			const truncated = meta !== null && typeof meta.truncated === "boolean" ? meta.truncated : false;
			const provider = meta !== null && typeof meta.provider === "string" ? meta.provider : null;
			const elapsedMs = meta !== null && typeof meta.elapsedMs === "number" && Number.isFinite(meta.elapsedMs) ? meta.elapsedMs : null;
			const count = meta !== null && typeof meta.count === "number" && Number.isInteger(meta.count) ? meta.count : null;
			const statusCode = meta !== null && typeof meta.statusCode === "number" && Number.isInteger(meta.statusCode) ? meta.statusCode : null;
			const length = meta !== null && typeof meta.length === "number" && Number.isInteger(meta.length) ? meta.length : null;
			const url = (meta !== null ? meta.url : void 0) ?? readString(readArgs(block), "url");
			const conversationUrl = metaKind === "fetch" && typeof meta.url === "string" ? meta.url : void 0;

			if (!settled) {
				return {
					state,
					card: kind === "search" ? { kind: "search", sources: [], truncated: false } : { kind: "fetch", url: url ?? "", statusCode: 0, truncated: false },
					meta: null,
					conversationUrl: void 0,
					kind
				};
			}
			if (kind === "search") {
				const sources = meta !== null ? readSources(meta.sources) : null;
				return {
					state,
					card: { kind: "search", sources: sources ?? [], truncated },
					meta: { provider, elapsedMs, count: count ?? (sources === null ? null : sources.length), truncated, statusCode: null, length: null },
					conversationUrl: void 0,
					kind
				};
			}
			return {
				state,
				card: { kind: "fetch", url: url ?? "", statusCode: statusCode ?? 0, truncated },
				meta: { provider, elapsedMs, count: null, truncated, statusCode, length },
				conversationUrl,
				kind
			};
		}
		/** Collapsed summary: the query list, else the fetched URL, else the recorded result head. */
		function summaryText(kind, queries, url, block) {
			const fallback = resultText(block);
			const recorded = fallback === null ? "" : firstLine(fallback);
			if (kind === "search") {
				if (queries.length > 0) return queries.map(firstLine).join(", ");
				return recorded;
			}
			if (typeof url === "string" && url !== "") return firstLine(url);
			return recorded;
		}
		/** Metadata tokens: provider, elapsed time, result count or content length, truncation flag. */
		function metaTokens(kind, meta) {
			const tokens = [];
			if (meta === null) return tokens;
			if (meta.provider !== null) tokens.push(`${copy.provider} ${meta.provider}`);
			if (meta.elapsedMs !== null) tokens.push(`${copy.elapsed} ${formatElapsed(meta.elapsedMs)}`);
			if (kind === "search") {
				if (meta.count !== null) tokens.push(copy.results(meta.count));
				if (meta.truncated) tokens.push(copy.sourcesTruncated);
			} else {
				if (meta.statusCode !== null) tokens.push(`${copy.http} ${String(meta.statusCode)}`);
				if (meta.length !== null) tokens.push(`${copy.length} ${formatBytes(meta.length)}`);
				if (meta.truncated) tokens.push(copy.contentTruncated);
			}
			return tokens;
		}
		/** Compact duration: `820ms`, `1.4s`, `12s`. */
		function formatElapsed(ms) {
			if (ms < 1000) return `${String(Math.max(0, Math.round(ms)))}ms`;
			if (ms < 10000) return `${(ms / 1000).toFixed(1)}s`;
			return `${String(Math.round(ms / 1000))}s`;
		}
		/** Compact byte size for the fetch content length. */
		function formatBytes(length) {
			if (length < 1024) return `${String(length)} B`;
			if (length < 1024 * 1024) return `${(length / 1024).toFixed(1)} KB`;
			return `${(length / (1024 * 1024)).toFixed(1)} MB`;
		}
		/** WebBlock chrome labels; mirrors the official `webBlockLabels` set. */
		const WEB_LABELS = {
			noResults: copy.noResults,
			sourcesTruncated: copy.sourcesTruncated,
			http: copy.http,
			contentTruncated: copy.contentTruncated,
			markdown: {
				code: { copyLabel: "Copy", copiedLabel: "Copied", toolbarLabels: {} },
				footnotes: "Footnotes"
			}
		};
		//#endregion

		//#region styles
		/** Row-scoped styles; colors and sizes come from the shell's design tokens so light and dark both match. */
		const css = [
			".bsRow{display:flex;flex-direction:column;min-width:0}",
			".bsBody{display:flex;flex-direction:column;gap:6px}",
			".bsQueries{display:flex;flex-direction:column;gap:2px;margin:0;padding:0;list-style:none}",
			".bsQuery{color:var(--dsw-alias-label-primary);font-size:var(--dsh-content-font-size,14px);line-height:calc(20px + var(--dsh-content-font-delta,0px));overflow-wrap:anywhere}",
			".bsMeta{display:flex;flex-wrap:wrap;gap:4px 10px;color:var(--dsw-alias-label-tertiary);font-size:12px;line-height:18px}",
			".bsMetaToken{white-space:nowrap}",
			".bsError{color:var(--dsw-alias-label-error,var(--dsw-alias-label-primary));white-space:pre-wrap;overflow-wrap:anywhere;font-size:var(--dsh-content-font-size,14px);line-height:calc(20px + var(--dsh-content-font-delta,0px))}",
			".bsSuffix{white-space:nowrap}",
			".bsInspect{align-self:flex-start;border:0;background:none;color:var(--dsw-alias-label-tertiary);cursor:pointer;font-size:12px;padding:2px 0}",
			".bsInspect:hover{color:var(--dsw-alias-label-primary)}"
		].join("");
		const STYLE_TAG_ID = "dsh-balanced-search/client.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(STYLE_TAG_ID) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "dsh-balanced-search";
			tag.dataset.pluginCss = STYLE_TAG_ID;
			tag.textContent = css;
			document.head.appendChild(tag);
		}
		//#endregion

		//#region view
		/** Leading glyph: globe for search, browse for fetch, matching the official web rows. */
		function leadingIcon(kind) {
			return kind === "fetch" ? react.createElement(IconBrowseOutlineRegular, { size: 14 }) : react.createElement(IconGlobeOutlineRegular, { size: 14 });
		}
		/** The `balanced` suffix that separates these cards from the official web tools. */
		function badge() {
			return react.createElement(TextShimmer, { className: "bsSuffix", children: `· ${copy.badge}` });
		}
		/** Expanded body: the queries or the URL, the WebBlock card, the provider line, and an optional inspect action. */
		function expandedBody(kind, queries, web, inspect, inspectLabel) {
			const children = [];
			if (kind === "search" && queries.length > 0) {
				children.push(react.createElement("ul", { className: "bsQueries", key: "queries" }, queries.map((query, index) => react.createElement("li", { className: "bsQuery", key: index }, query))));
			} else if (kind === "fetch" && typeof web.card.url === "string" && web.card.url !== "") {
				children.push(react.createElement("div", { className: "bsQuery", key: "url" }, web.card.url));
			}
			children.push(react.createElement(WebBlock, { key: "block", ...web.card, labels: WEB_LABELS }));
			const tokens = metaTokens(kind, web.meta);
			if (tokens.length > 0) {
				children.push(react.createElement("div", { className: "bsMeta", key: "meta" }, tokens.map((token, index) => react.createElement("span", { className: "bsMetaToken", key: index }, token))));
			}
			if (typeof inspect === "function") {
				children.push(react.createElement("button", { type: "button", className: "bsInspect", key: "inspect", onClick: inspect }, inspectLabel));
			}
			return react.createElement("div", { className: "bsBody" }, children);
		}
		/**
		 * One balanced web search or fetch call rendered with the official web card
		 * shell, distinguished by the `· balanced` title suffix.
		 */
		function BalancedWebRow(props) {
			const { toolName, block, inspect, useDisclosure } = props;
			const disclosure = useDisclosure();
			const expanded = disclosure !== void 0 && disclosure !== null ? disclosure.expanded === true : false;
			const toggle = disclosure !== void 0 && disclosure !== null && typeof disclosure.toggle === "function" ? disclosure.toggle : () => {};
			const queries = readQueries(readArgs(block));
			const web = readWeb(block, queries);
			const kind = web.kind;
			const running = web.state === "running" || web.state === "preparing";
			const failed = web.state === "error" || web.state === "stopped";
			const summary = summaryText(kind, queries, web.card.kind === "fetch" ? web.card.url : void 0, block);
			const title = kind === "fetch" ? copy.fetchTitle : copy.searchTitle;
			const collapsed = react.createElement(TextShimmer, null, summary === "" ? (running ? (kind === "search" ? copy.searching : copy.fetching) : title) : summary);
			const body = failed && summary === "" ? react.createElement("div", { className: "bsError" }, copy.failedPrefix) : expandedBody(kind, queries, web, inspect, copy.inspect);
			return react.createElement("div", { className: "bsRow", "data-variant": kind === "search" ? "search" : "read", "data-tool": toolName, "data-state": web.state, "data-balanced": "true" },
				react.createElement(DisclosureRow, {
					icon: leadingIcon(kind),
					title,
					open: expanded,
					expandable: true,
					expandOnRowClick: true,
					keepContentWhenOpen: true,
					running,
					onToggle: toggle,
					headerAccessory: badge(),
					titleClassName: "bsTitle",
					collapsedContent: collapsed
				}, body)
			);
		}
		//#endregion

		//#region apply
		/** Keyed Tool view keys owned by this plugin: the wire names of the balanced tools. */
		const TOOLVIEW_KEYS = ["balanced_search", "balanced_fetch"];
		/** Required service: the client slot registry. */
		const inject = ["slots"];
		/**
		 * Register the balanced Tool views. A keyed hit replaces the generic row, so
		 * these cards render exactly where the official `web_search` card does.
		 * @param ctx - Client root context.
		 */
		function apply(ctx) {
			ctx.slots.inject("tool.call.toolview", function* () {
				for (const key of TOOLVIEW_KEYS) {
					yield ctx.slots.register({
						name: "tool.call.toolview",
						key
					}, BalancedWebRow);
				}
			});
		}
		//#endregion

		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	}
});
