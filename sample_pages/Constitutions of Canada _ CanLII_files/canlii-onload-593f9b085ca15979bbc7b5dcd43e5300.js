var skipTabHistory = false;

const retinaScreen = "(-webkit-min-device-pixel-ratio: 2), (min-device-pixel-ratio: 2), (min-resolution: 192dpi)";
let originalRatio = (matchMedia(retinaScreen).matches) ? 2 : 1;
let previousZoom = Math.round(window.devicePixelRatio * 100);

function zoomBehaviours(init = false) {
	let zoom = Math.round(window.devicePixelRatio * 100);
	let ratio = (matchMedia(retinaScreen).matches) ? 2 : 1;

	function calculatedRatio(digit = 0) {
		let calculatedDensity = Math.round((window.screen.width / window.innerWidth) * 100);
		return Number((previousZoom / calculatedDensity).toFixed(digit));
	}

	if (init && calculatedRatio() === 1) {
		originalRatio = 1; // normal screen
	} else if (ratio < originalRatio) {
		originalRatio = 1; // ratio changed down (from Retina under 200%)
	} else if ((zoom / previousZoom === 2 && ratio / originalRatio === 2) || (originalRatio === 1 && previousZoom === 180)) {
		originalRatio = 2; // ratio changed up (to Retina)
	}

	$("body")
		.removeClass((i, className) => {
			return (className.match(/(^|\s)zoom-\d+/g) || []).join(' ');
		})
		.addClass("zoom-" + Math.round(zoom / originalRatio));
	previousZoom = zoom;
}

$(document).ready(function() {
	if (typeof Tipped != "undefined") {
		Tipped.setDefaultSkin('light');
	}
	
	$('ul.nav-tabs a[data-bs-toggle="tab"]').on('shown.bs.tab', function (e) {
		// store the currently selected tab in the hash value
		if (skipTabHistory == false) {
			let hash = e.target.hash;
			if(history.pushState) {
				history.pushState(null, null, hash);
			} else {
				window.location.hash = hash; //Polyfill for old browsers
			}
		} else {
			skipTabHistory = false;
		}
	});

	manageSwitchTab();

    $('select#navArbitratorSelector, select#navYearsSelector, select#navMonthsSelector').on('change', function() {
    	if (this.value != null && this.value != "") {
    		window.location.href = this.value;
    	}
	});
	
	initRowFilters();
	fixSmartphoneDisplay();

	$("div#canlii-login a").each(function () {
		let currentHref = $(this).attr("href");
		$(this).attr("href", currentHref + window.location.href);
	});

	$("div#canlii-login span.disabled").each(function () {
		$(this).tooltip({
			placement : 'bottom',
			title: getLoginDisabledMsg(),
		});
	});

	$("div#canlii-lang-toggler .dropdown-menu a").on("click", function(e) {
		languageSelected(e);
	});

	$("div#canlii-lang-toggler .dropdown-menu a").on("keypress", function(e) {
		if (e.keyCode === 13) {
			languageSelected(e);
		}
	});

	$("#toggleAudio").on("click", function(e) {
		toggleAudioCaptcha();
	});

	$("#toggleAudio").on("keypress", function(e) {
		if (e.keyCode === 13) {
			toggleAudioCaptcha();
		}
	});

	loadMobileHighlight();
	loadSurvey();
	// loadSurveyAlert();
	loadTheme();
	loadCookieConsent();
	zoomBehaviours(true);
	window.addEventListener("resize", zoomBehaviours, false);
});

function languageSelected(e) {
	let element = $(e.currentTarget);
	let cookieValue = element[0].dataset['lang'];
	setCookie('userLocale', cookieValue, 365);
	setCookie('localeChangeDate', new Date().toISOString(), 365);

	let cacheBusterUrl = addQueryParam(window.location.href, "noCache", cookieValue);
	
	// Le paramètre pour la langue de l'index de recherche est toujours dans l'url (pour éviter
	// de partager un url de recherche qui utilise un index différent). Si l'usager n'a pas
	// modifié cette option dans les filtres, nous devons modifier le paramètre pour que la
	// recherche se fasse dans la langue choisie.
	if (cacheBusterUrl.includes("indexLang=en") && cookieValue === "fr") {
		cacheBusterUrl = cacheBusterUrl.replace("indexLang=en", "indexLang=fr");
	} else if (cacheBusterUrl.includes("indexLang=fr") && cookieValue === "en") {
		cacheBusterUrl = cacheBusterUrl.replace("indexLang=fr", "indexLang=en");
	}
	
	if(typeof getGarState !== "undefined" && getGarState() !== undefined){
		cacheBusterUrl = addQueryParam(cacheBusterUrl, "garState", getGarState());
	}
	window.location.href = cacheBusterUrl;
}

function initRowFilters() {
	let toFilter = $("#legislationsContainer li.filterable, tr.tribunalRow, #decisionsListing div.row, #decisionsListing tr, #doctrineContainer li.filterable, #doctrineContainer tr.filterable, .canlii-sidebar-content li.filterable");

	$(document).on('keyup', '#basicItemsFilter, #doctrineItemsFilter', function () {
		let value = normalizeString($(this).val());

		let matchCount = 0;

		toFilter.each(function() {
			var normalizedText = normalizeString($(this).text());
			var otherValues = $(this).attr("othervalues");
			if (otherValues != undefined) {
				var normalizedOtherValues = normalizeString(otherValues);
			}
			var match = (normalizedText.indexOf(value) > -1) ||
				(normalizedOtherValues != undefined && normalizedOtherValues.indexOf(value) > -1);

			if (match) {
				matchCount++;
			}

			if ($(this).hasClass("d-flex") || $(this).hasClass("d-none")) {
				if (match) {
					$(this).removeClass("d-none");
				} else {
					$(this).addClass("d-none");
				}
			} else {
				$(this).toggle(match);
			}
		});

		if (matchCount == 0) {
			$(this).addClass("is-invalid");
		} else {
			$(this).removeClass("is-invalid");
		}
	});

	$(document).on('input', '#basicItemsFilter, #doctrineItemsFilter', (evt) => {
		if (evt.target.value.length === 0) {
			$("#basicItemsFilter, #doctrineItemsFilter").removeClass("is-invalid");
			toFilter.removeClass("d-none");
		}
	});
}

function manageSwitchTab() {
	// switch to the currently selected tab when loading the page
	if ($.isFunction($.fn.tab)) {
		loadCurrentTab();
	}
	
	// switch to the currently selected tab on browser back/forward
	$(window).on('popstate', function(e) {
		skipTabHistory = true;
		loadCurrentTab();
	});
}

function loadCurrentTab() {
	if (window.location.hash === "") {
		// hash will be empty if we come from another page
		$('ul.nav-tabs a').first().tab('show');
	} else {
		$('ul.nav-tabs a[href="' + window.location.hash + '"]').tab('show');
	}
}

function toggleAudioCaptcha() {
	$('#captchaTag').toggle();
	$('#audioCaptchaTag').toggle();
	if ($('#audioCaptchaTag').css("display") == "none") {
		$('#captchaResponse').focus();
	} else {
		$('#audioCaptchaTag').focus();
	}
}

function loadSurvey() {
	$("div#surveyModal button.rater").on("click", function(e) {
		selectSurveyStar(e);
	});
	
	$("div#surveyModal button.rater").on("keypress", function(e) {
		if (e.keyCode === 13) {
			selectSurveyStar(e);
		}
	});
	
	$("div#surveyModal button#surveySubmit").on("click", function(e) {
		var selectedRating = $("div#surveyModal i.fa-star.rate-selected");
		if (selectedRating == null || selectedRating.length == 0) {
			$("div#surveyModal span#ratingWarning").show();
		} else {
			$("div#surveyModal span#ratingWarning").hide();
			
			var rating = selectedRating.attr("id").split("-").pop();
			sendSurvey(rating);
			
			$('div#surveyModal').modal('hide');
		}
	});
	
	$("div#surveyModal").on("hidden.bs.modal", function (e) {
		// reset values
		$("div#surveyModal i.fa-star").each(function () {
			$(this).removeClass("rate-selected");
			$(this).css("color", "#d7eb00");
		});
		$("div#surveyModal textarea#surveyMessage").val("");
	});
}

function selectSurveyStar(e) {
	var element = $(e.currentTarget);
	var rateValue = element.children().first().attr("id").split("-").pop();
	for (var i=1; i<=5; i++) {
		if (i <= rateValue) {
			$("i#rate-" + i).css("color", "#ebb000");
			$("i#rate-" + i).css("border-bottom-style", "solid");
			$("i#rate-" + i).css("border-bottom-width", "2px");
			$("i#rate-" + i).css("padding-bottom", "2px");
		} else {
			$("i#rate-" + i).css("color", "#d7eb00");
			$("i#rate-" + i).css("border-bottom-width", "0");
		}
		
		if (i == rateValue) {
			$("i#rate-" + i).addClass("rate-selected");
		} else {
			$("i#rate-" + i).removeClass("rate-selected");
		}
	}
}

function loadTheme() {
	if (isIe()) {
		document.querySelector("#darkModeCb").disabled = true;
		$("#darkOption").tooltip({
			placement : 'right',
			title: getUnsupportedBrowserString()
		});
	}

	if (isDarkMode()) {
		let darkModeCb = document.querySelector("#darkModeCb");
		
		// may be null if we are inside an iframe without the canlii footer
		if (darkModeCb != null) {
			darkModeCb.checked = true;
		}
		
		if (typeof Tipped != "undefined") {
			Tipped.setDefaultSkin('dark');
		}
	}

	$("input#darkModeCb").on("click", function(e) {
		toggleDarkMode(e);
	});
}

function toggleDarkMode(e) {
	let elementInLegislationPagesOnly = $("div.canliidocumentcontent");

	if (!isDarkMode()) {
		addDarkStylesheet();
		
		if (typeof Tipped != "undefined") {
			Tipped.setDefaultSkin('dark');

			// need to re-create all tipped, so their style can be updated
			recreateAllScrollMarkerTips(elementInLegislationPagesOnly != null);
			recreateFootnotesTooltips();
		}
		
		setCookie('canliiTheme', "dark", 365);
	} else {
		removeDarkStylesheet();
		
		if (typeof Tipped != "undefined") {
			Tipped.setDefaultSkin('light');

			// need to re-create all tipped, so their style can be updated
			recreateAllScrollMarkerTips(elementInLegislationPagesOnly != null);
			recreateFootnotesTooltips();
		}
		
		setCookie('canliiTheme', "default", 365);
	}
	// keep open
	e.stopPropagation();
}

function loadCookieConsent() {
	let cookieConsent = readCookie("cookieConsent");
	
	// manage old cookie value
	if (cookieConsent != null && cookieConsent == "true") {
		eraseCookie("cookieConsent");
		cookieConsent = readCookie("cookieConsent");
	}
	
	if (cookieConsent == null) {
		// do not block the content on the privacy page
		let currentHref = window.location.href;
		if (!currentHref.includes("en/info/privacy.html") && !currentHref.includes("fr/info/confidentialite.html")) {
			$("div#cookieConsentBlocker").show();
		}
        $("div#cookieConsentBanner").show();
    }
	
	$("button#understandCookieConsent, button#acceptAllCookies").click(() => {
	    setCookie("cookieConsent", CookieConsent.all, 365);
	    $("div#cookieConsentBlocker").fadeOut(300);
	    $("div#cookieConsentBanner").fadeOut(300);
		CanliiAnalytics.enableSnowplow()
	});
	
	$("button#acceptSelectedCookies").on("click", function() {
		let perfSelected = $("input#performanceCookiesCb").is(":checked");
		let funcSelected = $("input#funcCookiesCb").is(":checked");
		
		if (perfSelected && funcSelected) {
			setCookie("cookieConsent", CookieConsent.all, 365);
			CanliiAnalytics.enableSnowplow()
		} else if (!perfSelected && !funcSelected) {
			setCookie("cookieConsent", CookieConsent.necessary, 365);
			
			// delete cookies based on the user choice
			for (let [key, value] of CookiesMap) {
				if (value !== CookieConsent.necessary) {
					eraseCookie(key);
				}
			}
			
			// to remove all lexbox widgets
			$.get("/delete-lexbox-cookies");
			window.location.reload();
			
		} else if (perfSelected) {
			setCookie("cookieConsent", CookieConsent.perf, 365);
			
			// delete cookies based on the user choice
			for (let [key, value] of CookiesMap) {
				if (value !== CookieConsent.necessary && value !== CookieConsent.perf) {
					eraseCookie(key);
				}
			}
			
			// to remove all lexbox widgets
			$.get("/delete-lexbox-cookies");
			window.location.reload();
			
		} else if (funcSelected) {
			setCookie("cookieConsent", CookieConsent.func, 365);
			
			// delete cookies based on the user choice
			for (let [key, value] of CookiesMap) {
				if (value !== CookieConsent.necessary && value !== CookieConsent.func) {
					eraseCookie(key);
				}
			}
		}
		
		$("div#cookieConsentBlocker").fadeOut(300);
		$("div#cookieConsentBanner").fadeOut(300);
	});

	// keyboard support
	$("a#cookieConsentToggler").on("keypress", function(e) {
		if (e.keyCode === 13) {
			$("#cookieConsentModal").modal("toggle");
		}
	});

	// cookie types description togglers
	$('div#cookieConsentContainer .cookieType').on("click", function() {
		let descriptionDiv = $(this).parent().next();
		
	    if (descriptionDiv.is(':hidden')) {
			descriptionDiv.slideDown(); 
			$(this).find("button.descriptionToggler i").removeClass("fa-plus");
			$(this).find("button.descriptionToggler i").addClass("fa-minus");
		} else {
			descriptionDiv.slideUp(); 
			$(this).find("button.descriptionToggler i").removeClass("fa-minus");
			$(this).find("button.descriptionToggler i").addClass("fa-plus");
		}
	});
	
	// check or uncheck switches based on the consent current value
	$("div#cookieConsentModal").on("show.bs.modal", () => {
		let cookieConsent = readCookie("cookieConsent");
		switch(cookieConsent) {
			case CookieConsent.all:
				$("input#performanceCookiesCb").prop("checked", true);
				$("input#funcCookiesCb").prop("checked", true);
				break;
			case CookieConsent.necessary:
				$("input#performanceCookiesCb").prop("checked", false);
				$("input#funcCookiesCb").prop("checked", false);
			    break;
			case CookieConsent.perf:
				$("input#performanceCookiesCb").prop("checked", true);
				$("input#funcCookiesCb").prop("checked", false);
			    break;
			case CookieConsent.func:
				$("input#performanceCookiesCb").prop("checked", false);
				$("input#funcCookiesCb").prop("checked", true);
			    break;
			default:
				$("input#performanceCookiesCb").prop("checked", false);
				$("input#funcCookiesCb").prop("checked", false);
		    	break;
		}
	});

	$("a#cookiesResetter").on("click", function (e) {
		e.preventDefault();
		eraseCookies($(this));
		return false;
	});
	
	$("a#cookiesResetter").on("keypress", function(e) {
		e.preventDefault();
		if (e.keyCode === 13) {
			eraseCookies($(this));
		}
		return false;
	});
}

function loadSurveyAlert() {
	let surveyAlertClosed = readCookie("hideSurveyAlert");
	if (surveyAlertClosed == null) {
		$("div#surveyAlert").show("fast");
	}

	$("button#surveyAlertCloser, a#surveyAlertLink").on("click", function() {
		$("div#surveyAlert").hide("fast");
		setCookie('hideSurveyAlert', "true", 120);
	});
}

function loadMobileHighlight() {
	$("div#highlight-mobile-button").on("click", function() {
		let bottomBarDisplay = $(".bottom-bar").css("display");
		if (bottomBarDisplay != null && bottomBarDisplay === "none") {
			$(".bottom-bar").css("display", "flex");
		} else {
			$(".bottom-bar").css("display", "none");
		}
	});

	$("#mobile-highlight-button").on("click", function () {
		_highlight.highlightFromInput("#mobile-highlight-input");
	});

	$("#mobile-highlight-input").on("keyup", function(e) {
		if (e.which === 13) {
			_highlight.highlightFromInput("#mobile-highlight-input");
		}
	});
}
