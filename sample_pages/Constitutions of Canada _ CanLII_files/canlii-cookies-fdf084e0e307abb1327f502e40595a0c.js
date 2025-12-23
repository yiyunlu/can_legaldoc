const CookieConsent = {
	all: "ALL",
	necessary: "NECESSARY",
	perf: "PERFORMANCE",
	func: "FUNCTIONALITY",
}

const CookiesMap = new Map([
	["cookieConsent", CookieConsent.necessary],
	["unsupportedBrowser", CookieConsent.necessary],
	["userLocale", CookieConsent.necessary],
	["localeChangeDate", CookieConsent.necessary],
	
	["SESSIONID", CookieConsent.perf],
	
	["canliiTheme", CookieConsent.func],
	["COPID", CookieConsent.func],
	["expandResults", CookieConsent.func],
	["framedResults", CookieConsent.func],
	["hideSurveyAlert", CookieConsent.func],
	["garExpandedSize", CookieConsent.func],
	["garExpanded", CookieConsent.func],
	["closedSurveyAlert", CookieConsent.func],
	
	["lexbox.clientCode", CookieConsent.func],
	["KEYCLOAK_ADAPTER_STATE", CookieConsent.func],
	["KEYCLOAK_ADAPTER_STATE_2", CookieConsent.func],
	["KEYCLOAK_ADAPTER_STATE_3", CookieConsent.func],
	["KEYCLOAK_ADAPTER_STATE_4", CookieConsent.func],
	["KEYCLOAK_ADAPTER_STATE_5", CookieConsent.func],
	["KEYCLOAK_ADAPTER_STATE_6", CookieConsent.func],
	["KEYCLOAK_ADAPTER_STATE_REALM", CookieConsent.func],
	["KC_REDIRECT", CookieConsent.func],
	["lexbox.locale", CookieConsent.func],
	["lexbox-api.jsessionid", CookieConsent.func]
]);

function isConsented(cookieType) {
	if (cookieType == null) {
		// cookie not supported
		return false;
	}
	
	let cookieConsent = readCookie("cookieConsent");
	switch(cookieType) {
		case CookieConsent.necessary:
		    return true;
		case CookieConsent.perf:
		    if (cookieConsent != null && (cookieConsent.includes(CookieConsent.all) || cookieConsent.includes(CookieConsent.perf))) {
				return true;
			} else {
				return false;
			}
		case CookieConsent.func:
		    if (cookieConsent != null && (cookieConsent.includes(CookieConsent.all) || cookieConsent.includes(CookieConsent.func))) {
				return true;
			} else {
				return false;
			}
		default:
	    	return false;
	}
}

function acceptLexboxCookies() {
	let cookieConsent = readCookie("cookieConsent");
	switch(cookieConsent) {
		case CookieConsent.necessary:
		    setCookie("cookieConsent", CookieConsent.func, 365);
		    break;
		case CookieConsent.perf:
		    setCookie("cookieConsent", CookieConsent.all, 365);
		    break;
		default:
	    	// nothing to do
	}
}

function setCookie(cookieName, value, duration) {
	let cookieType = CookiesMap.get(cookieName);
	
	if (isConsented(cookieType)) {
		var expiration = "";

		if (duration) {
			var endTime = new Date();
			endTime.setTime(endTime.getTime()+(duration*24*3600*1000));
			expiration = "; expires=" + endTime.toGMTString();
		}
	
		document.cookie = cookieName + "=" + value + expiration + "; path=/";
	}
}

function eraseCookie(cookieName) {
	document.cookie = cookieName + "=; expires=" + new Date(0).toUTCString() + "; path=/";
}

function eraseCookies(a) {
	let cookies = document.cookie.split(';');
 
	for (var i=0; i<cookies.length; i++) {
		eraseCookie(cookies[i]);
	}

	// for HttpOnly cookies
	$.get("/delete-cookies")
		.fail(function () {
			a.text(a.data("fail")).addClass("error");
			a.append('&nbsp;<i aria-hidden="true" class="fas fa-ban"></i>');
		})
		.done(function () {
			a.text(a.data("success")).addClass("success");
			a.append('&nbsp;<i aria-hidden="true" class="fas fa-check"></i>');
		});
}

function readCookie(cookieName) {
	var nameLookup = cookieName + "=";
	var cookies = document.cookie.split(";");

	for (var i=0; i < cookies.length; i++) {
		let cookie = cookies[i];
		while (cookie.charAt(0)==' ') cookie = cookie.substring(1, cookie.length);
		if (cookie.indexOf(nameLookup) == 0) {
			return cookie.substring(nameLookup.length, cookie.length);
		}
	}

	return null;
}
