/** 
 * Many functions in this object returns Promises. This way, if an analytics call 
 * fails, the main javascript will not be affected.
 */
const ANALYTICS_BASE = $('#analytics-script').data("analyticsBase");

const SEARCH_SCHEMA = "iglu:com.lexum/search/jsonschema/1-0-0"
const AUTOCOMPLETE_SCHEMA = "iglu:com.lexum/autocomplete/jsonschema/1-0-0"
const LOAD_MORE_SCHEMA = "iglu:com.lexum/load-more/jsonschema/1-0-0"
const SEARCH_SCROLL_SCHEMA = "iglu:com.lexum/search-scroll/jsonschema/1-0-0"
const SEARCH_CONTEXT_SCHEMA = "iglu:com.lexum/search-context/jsonschema/1-0-0"
const RESULT_CONTEXT_SCHEMA = "iglu:com.lexum/result-context/jsonschema/1-0-0"
const READING_PANE_CONTEXT_SCHEMA = "iglu:com.lexum/reading-pane-context/jsonschema/1-0-0"
const HIGHLIGHT_SCROLL_SCHEMA = "iglu:com.lexum/highlight-scroll/jsonschema/1-0-0"
const HIGHLIGHT_TERM_CLICK_SCHEMA = "iglu:com.lexum/highlight-term-click/jsonschema/1-0-0"
const PRINT_SCHEMA = "iglu:com.lexum/print/jsonschema/1-0-0"
const COPY_PARAG_TOOL_SCHEMA = "iglu:com.lexum/copy-parag-tool/jsonschema/1-0-0"

var CanliiAnalytics = {
	enabled: false,
	searchScrollingInitialized: false,
	resultIdsCurrentlyVisible: new Set(),
	resultId: undefined,

	analyticsEnabled: function(){
		return ANALYTICS_BASE !== "";
	},

	analyticsPermissionGranted: function() {
		let cookieConsent = readCookie("cookieConsent");
		return cookieConsent != null && (cookieConsent.includes(CookieConsent.all) || cookieConsent.includes(CookieConsent.perf))
	},
	
	transformResults: function(results) {
		let transformedResults = [];
		if (results != null && results.length > 0) {
			results.forEach((result) => {
				var uuid = (result.uUId || result.uuid);
				transformedResults.push({ 
					id: uuid, 
					title: (result.exactTitle || result.contributionTitle),
					reference: (result.exactReference || result.citation),
					path: (result.path || undefined), 
					url: (result.url || undefined), 
					type: result.type, 
					coll: result.collectionTitle, 
					jur: result.jurisdictionTitle, 
					date: (result.judgmentDate || undefined), 
					citedCount: result.citationCount,
				});
			});
		}
		
		return transformedResults;
	},
	
	search: async function(searchUrl, results, trigger, spellcheck, autocompleteQuery, autocompleteSearchId) {
		snowplow('refreshLinkClickTracking');

		if (trigger == undefined) {
			if (window.location.href.includes("linkedNoteup=")) {
				trigger = AppUtils.linkedNoteupTrigger;
			} else {
				trigger = AppUtils.unknownTrigger;
			}
		}
		
		let autocorrect = null;
		if (spellcheck != undefined && spellcheck != null) {
			if (spellcheck.textQuery != null && spellcheck.textQuery != "") {
				autocorrect = {};
				autocorrect.text = spellcheck.textQuery;
				autocorrect.field = "text";
			} else if (spellcheck.idQuery != null && spellcheck.idQuery != "") {
				autocorrect = {};
				autocorrect.text = spellcheck.idQuery;
				autocorrect.field = "id";
			}
		}

		let extractedParams = extractParams(searchUrl, autocompleteQuery, autocompleteSearchId);
		let documentTypeFacets = {};
		for (const elem of app.models.type.getAllTypes()) {
			documentTypeFacets[elem.id] = parseInt(elem.count.replaceAll(",", ""))
		}
		
		this.resultIdsCurrentlyVisible = this.collectResultIdsInViewport()
		snowplow('trackSelfDescribingEvent', {
			event: {
				schema: SEARCH_SCHEMA,
				data: {
					searchId: (autocompleteSearchId || extractedParams["searchId"]),
					precedingSearch: this.getPreviousSearch(),
					searchParams: extractedParams,
					documentTypeFacets: documentTypeFacets,
					autocorrect: (autocorrect || undefined),
					trigger: trigger,
					results: this.transformResults(results),
					resultsInViewport: Array.from(this.resultIdsCurrentlyVisible)
				}
			}
		});
	},

	autocomplete: async function(searchUrl, results, autocompleteQuery, searchId) {
		// snowplow('refreshLinkClickTracking'); // TODO track clicks on autocomplete results
		
		let extractedParams = extractParams(searchUrl, autocompleteQuery, searchId);

		// this.resultIdsCurrentlyVisible = this.collectResultIdsInViewport() // TODO gather visible autocompletes
		snowplow('trackSelfDescribingEvent', {
			event: {
				schema: AUTOCOMPLETE_SCHEMA,
				data: {
					searchId,
					precedingSearch: this.getPreviousSearch(),
					searchParams: extractedParams,
					results: this.transformResults(results),
					resultsInViewport: Array.from(this.resultIdsCurrentlyVisible)
				}
			}
		});
	},

	isReadingPaneActivated: function(){
		var readingPane = typeof(app) != "undefined" && app?.models?.resultsFrame?.getFramed()
		var readingPaneFromIframe = window.parent?.app?.models?.resultsFrame?.getFramed()
		var inReadingPane = Boolean(readingPane || readingPaneFromIframe) // convert undefined to false
		return inReadingPane;
	},

	isReadingPaneLoaded: function(){
		const style = document.querySelector("#searchDocumentFrame")?.getAttribute("style");
		return style != null && style != "loading";
	},
	
	appendSearch: async function(searchUrl, results) {
		snowplow('refreshLinkClickTracking');

		let extractedParams = extractParams(searchUrl);
		
		snowplow('trackSelfDescribingEvent', {
			event: {
				schema: LOAD_MORE_SCHEMA,
				data: {
					page: parseInt(extractedParams["page"]),
					newResults: this.transformResults(results),
				}
			}
		})
	},
	
	getPreviousSearch: function() {
		let previousSearch = null;
		let previousSearchId = app.models.searchId.getPreviousSearchId();
		
		if (previousSearchId == null) {
			let neww = {};
			if (app._origJurisdictionValue != null) {
				neww.jId = app._origJurisdictionValue + ",unspecified";
			}
			
			if (app._origDocumentTypeValue != null) {
				neww.type = app._origDocumentTypeValue;
			}
			
			if (app._origCourtValue != null) {
				neww.ccId = app._origCourtValue;
			}
			
			if (app._origDoctrineWorkTypeValue != null) {
				neww.docWt = app._origDoctrineWorkTypeValue;
			}
			
			previousSearch = { new: neww };
			
		} else {
			previousSearch = { id: previousSearchId }
		}
		
		return previousSearch;
	},

	getResultId: function() {
		return extractParams(window.location.href)["resultId"];
	},
	
	searchResultMissingCitNetTerms: async function() {
		let data = {
			searchBatch: {
				eventType: "MISSING_CITNET_TERMS", 
				event: { 
				}
			}
		};
	
	},
	
	highlightScroll: async function(index, total, direction) {
		snowplow('trackSelfDescribingEvent', {
			event: {
				schema: HIGHLIGHT_SCROLL_SCHEMA,
				data: {
					currentTermIndex: parseInt(index),
					totalTerms: parseInt(total),
					direction
				}
			}
		});
	},
	
	highlightTermClicked: async function(term, active) {
		snowplow('trackSelfDescribingEvent', {
			event: {
				schema: HIGHLIGHT_TERM_CLICK_SCHEMA,
				data: { 
					term: term,
					active: active
				}
			}
		});
	},

	/**
	 * This is called on Canlii's search pages
	 */
	initSearchScrollingEvent: function() {
		if(!CanliiAnalytics.searchScrollingInitialized){
			snowplow('addGlobalContexts', [this.searchScrollContextGenerator]);

			// scrolling events needs to be throttled
			document.addEventListener('scroll', (e) => {
				if(CanliiAnalytics.isReadingPaneActivated() && CanliiAnalytics.isReadingPaneLoaded()){
					// doc scroll
				}else{
					// search scrolling
					this.accumulateResultIdsInViewport()
				}
			});
			
			document.querySelector("#searchResultsWrapper").addEventListener('scroll', () => {
				// search scrolling
				this.accumulateResultIdsInViewport()
			});
			CanliiAnalytics.searchScrollingInitialized = true
		}
	},

	collectResultIdsInViewport(){
		let resultIdsInViewport = [];
		$("div#searchResults").find('[data-result-uuid]').each(function() {
			let element = $(this);
			if (isElementInViewport(element)) {
				resultIdsInViewport.push(element.data("result-uuid"));
			}
		});
		return new Set(resultIdsInViewport);
	},
	
	buildPageViewportObject: function() {
		return {
			clientHeight: document.documentElement.clientHeight,
			clientWidth: document.documentElement.clientWidth,
		};
	},
	
	initPrintingEvent: function(forDoctrine) {
		if (forDoctrine) {
			$("li#nav-more ul.dropdown-menu li").on("click", $.proxy(function() {
				this.print();
			}, this));
		}
		
		if (window.matchMedia) {
			var mediaQueryList = window.matchMedia('print');
			mediaQueryList.addListener(function(mql) {
				if (mql.matches) {
					CanliiAnalytics.print();
				}
			});
		
		}
	},
	
	print: function () {
		snowplow('trackSelfDescribingEvent', {
			event: {
				schema: PRINT_SCHEMA,
				data: {}
			}
		})
	},
	
	// copyParagraphTextClicked, copyParagraphCitationClicked, copyParagraphLinkClicked
	copyParagraphToolClicked: function (paragNumber, type, copied) {
		snowplow('trackSelfDescribingEvent', {
			event: {
				schema: COPY_PARAG_TOOL_SCHEMA,
				data: { 
					paragNumber,
					type,
					copied
				}
			}
		});
	},
	
	initAnalytics: function() {
		this.resultId = this.getResultId()
		
		if(CanliiAnalytics.analyticsPermissionGranted()){
			this.enableSnowplow()
		}
	},

	enableSnowplow: async function(){
		var snowplow_endpoint
		if(window.SNOWPLOW_OVERRIDE){
			snowplow_endpoint = SNOWPLOW_OVERRIDE
		}else{
			snowplow_endpoint = new URL(ANALYTICS_BASE, document.location).href
		}
		window.snowplow('newTracker', 'sp', snowplow_endpoint, {
			appId: 'canlii',
			discoverRootDomain: true,
			cookieSameSite: 'Lax', // Recommended
			contexts: {
			  webPage: true, // default, can be omitted
			  browser: true,
			  session: true,
			  gelocation: true,
			},
			eventMethod: "beacon",
			stateStorageStrategy: 'cookieAndLocalStorage',
		});

		snowplow('addGlobalContexts', [CanliiAnalytics.searchContextGenerator, CanliiAnalytics.readingPaneContextGenerator, CanliiAnalytics.resultContextGenerator.bind(CanliiAnalytics)]);
		
		snowplow('addPlugin',
			"https://cdn.jsdelivr.net/npm/@snowplow/browser-plugin-link-click-tracking@3.24.2/dist/index.umd.min.js",
			["snowplowLinkClickTracking", "LinkClickTrackingPlugin"]
		);
		  
		snowplow("enableActivityTracking", {
			minimumVisitLength: 5,
			heartbeatDelay: 15
		})
		
		snowplow("trackPageView") // MUST be called AFTER enableActivityTracking
		snowplow('enableLinkClickTracking', {pseudoClicks: true});

		CanliiAnalytics.enabled = true
	},
	
	initDocumentEvents: async function(forDoctrine) {
		this.initPrintingEvent(forDoctrine);
	},
	
	initSearchEvents: async function() {
		this.initSearchScrollingEvent();
	},

	createSessionId: function() {
		return getFormattedNowDate() + "/" + generateRandomUuid();
	},
	
	getSessionId: function() {
		return readCookie(CanliiAnalytics.sessionCookieName);
	},

	accumulateResultIdsInViewport: function() {
		this.collectResultIdsInViewport().forEach((result) => {
			this.resultIdsCurrentlyVisible.add(result)
		})
	},

	searchScrollContextGenerator: function(args) {
		if (args.eventType == 'pp' && CanliiAnalytics.resultIdsCurrentlyVisible.size > 0) { // page pings, once a search was made
			CanliiAnalytics.accumulateResultIdsInViewport();
			const data = {
				schema: SEARCH_SCROLL_SCHEMA,
				data: { 
					resultIdsSeen: Array.from(CanliiAnalytics.resultIdsCurrentlyVisible)
				},
			};
			CanliiAnalytics.resultIdsCurrentlyVisible = CanliiAnalytics.collectResultIdsInViewport();

			return data;
		}
	},

	searchContextGenerator: function(){
		const searchId = extractSearchId()
		if(searchId) {
			return {
				schema: SEARCH_CONTEXT_SCHEMA,
				data: {
					searchId
				}
			}
		}
	},

	resultContextGenerator: function(){
		if(this.resultId){
			var data = {
				schema: RESULT_CONTEXT_SCHEMA,
				data: {
					resultId: this.resultId
				}
			}
			return data
		}
	},

	readingPaneContextGenerator: function(){
		return {
			schema: READING_PANE_CONTEXT_SCHEMA,
			data: {
				readingPane: CanliiAnalytics.isReadingPaneActivated()
			}
		}
	},

	scrollContextGenerator: function(args){
		if (args.eventType == 'pp'){
			var result = {
				schema: DOC_SCROLL_CONTEXT_SCHEMA,
				data: {
					...CanliiAnalytics.scroll
				}
			}
			CanliiAnalytics.resetScroll()
			return result
		} 
	},
};

function extractParams(path, autocompleteQuery, autocompleteSearchId) {
	let decodedPath = decodeURIComponent(path);
	let params = {};

	if(decodedPath != "") {
		let lang = "en"
		if (decodedPath.startsWith("/fr")) {
			lang = "fr"
		}
		params["lang"] = lang;
		
		let splittedPath = decodedPath.split('?');
		let paramString = splittedPath[1];
		
		if (paramString != undefined) {
			let params_arr = paramString.split('&');
		
			for (let i = 0; i < params_arr.length; i++) {
				let pair = params_arr[i].split('=');
				params[pair[0]] = pair[1];
			}
		}
		
		if (autocompleteQuery != undefined) {
			params["autocompleteQuery"] = autocompleteQuery;
			
			if (splittedPath[0].includes("idCompletion")) {
				params["autocompleteType"] = "id";
				delete params.id;
			} else if (splittedPath[0].includes("noteupCompletion")) {
				params["autocompleteType"] = "noteup";
			}
		}
	}
	
	if (autocompleteSearchId != undefined && autocompleteSearchId != null) {
		params["searchId"] = autocompleteSearchId;
	}

	return params;
}

function extractSearchId() {
	let searchId = app?.models?.searchId?.attributes.SEARCH_ID || extractParams(window.location.search)["searchId"]
	if (searchId == null) {
		// searchId may be in the search params in the url hash part
		let hashPart = window.location.hash;
		if (hashPart.includes("searchId=")) {
			let searchParams = hashPart.substring(hashPart.lastIndexOf("/"), hashPart.length);
			let splittedParams = searchParams.split('&');
			
			for (let i = 0; i < splittedParams.length; i++) {
				let pair = splittedParams[i].split('=');
				if (pair[0] == "searchId") {
					return decodeURIComponent(pair[1]);
				}
			}
		}
	}
	return searchId;
}

// initialize analytics
if (CanliiAnalytics.analyticsEnabled()) {
	CanliiAnalytics.initAnalytics();
} else {
	let functionNamesToOverride = Object.getOwnPropertyNames(CanliiAnalytics).filter(item => typeof CanliiAnalytics[item] === 'function');
	for (let i of functionNamesToOverride) {
		CanliiAnalytics[i] = function() {};
	}
}

