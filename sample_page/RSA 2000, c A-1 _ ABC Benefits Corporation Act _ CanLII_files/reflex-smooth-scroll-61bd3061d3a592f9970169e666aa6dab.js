// This is the amount of seconds before the notification box autocloses
var targetText = "";
var language = "en";
var sectionLabel = null;
var _params = null;

var REFLEX2_NOTIFICATION_I18N = {
  "en": {
      "JURISDICTION_LABEL"	: "Jurisdiction",
      "TITLE_LABEL"		: "Title",
      "CITATION_LABEL"		: "Citation",
      "LOCATION_LABEL"		: "Location",
      "SECTION_LABEL"		: "s",
      "SUBSECTION_LABEL"	: "s",
      "SEARCH_LABEL"		: "Searching...",
      "NOT_FOUND"		: "not found",
      "SECTION"			: "Section",
      "TITLE"			: "Citation <a href=\"/en/info/reflex.html\">resolved</a> by CanLII"
  },
  "fr": {
      "JURISDICTION_LABEL"	: "Juridiction",
      "TITLE_LABEL"		: "Titre",
      "CITATION_LABEL"		: "Référence",
      "LOCATION_LABEL"		: "Localisation",
      "SECTION_LABEL"		: "art",
      "SUBSECTION_LABEL"	: "art",
      "SEARCH_LABEL"		: "Recherche...",
      "NOT_FOUND"		: "introuvable",
      "SECTION"			: "Article",
      "TITLE"			: "Référence <a href=\"/fr/info/reflex.html\">résolue</a> par CanLII"
  }
};

var DISABLED_JURISDICTIONS = {
  "pe" : "",
  "sk" : "",
  "yk" : "",
  "nu" : "",
  "nt" : ""
};

jQuery(document).ready(function($){

    //handle the case of anchors within legislations
    $('a[class="reflex2-link"][href^="#"][href$="smooth"]').on('click', function(){

        var hash = $(this).attr('href');
        updateDoc(_params, hash);
        if (hash == "" || hash == null) {
            log("No hash present, returning");
            return;
        }

        // !!! keep next line in case we want a persistent notification pop-up
        // $("#reflex2-notification-box").moveDown(400);

        // Check that the hash is made for this script.
        if (hash.match("#(.*)_smooth$") == false) {
            log("No smooth, returning");
            return;
        }

        //Event that removes the notification box when the user clicks on the X
        $("#reflex2-notification-box-close-button-div").click(function(){
            $("#reflex2-notification-box").remove();
            return false;
        });

        var id = hash.replace(/#(.*)_smooth/, function(match, idMatch) {
            idMatch = idMatch.replace(/[^a-zA-Z0-9-]/g, "_");
            return "#" + idMatch;
        });

		var sectionHash = id.replace(/(subsec|par).*/, '');

        // Anchor to scroll to
        var jqueryAnchor = $(id);
		var jQueryAnchorStripSubsection = $(sectionHash);

        // If the anchor exists
        if (jqueryAnchor != null && jqueryAnchor.length) {
            // Scroll to it
            gotoAnchor(jqueryAnchor);
        } else if (jQueryAnchorStripSubsection != null && jQueryAnchorStripSubsection.length){
			gotoAnchor(jQueryAnchorStripSubsection);
		} else {
            // Else show an error message
            showError();
        }

    });

	// Check that there is a hash to scroll to
	log("Checking hash: " + document.location.hash);
	var hash = document.location.hash;
	if (hash == "" || hash == null) {
		log("No hash present, returning");
		return;
	}

	// Check that the hash is made for this script.
	if (hash.match("#(.*)_smooth$") == false) {
		log("No smooth, returning");
		return;
	}

	//Event that removes the notification box when the user clicks on the X
	$("#reflex2-notification-box-close-button-div").click(function(){
		$("#reflex2-notification-box").remove();
		return false;
	});

	var id = hash.replace(/#(.*)_smooth/, function(match, idMatch) {
		idMatch = idMatch.replace(/[^a-zA-Z0-9-]/g, "_");
		return "#" + idMatch;
	});

	var sectionHash = id.replace(/(subsec|par).*/, '');

	// Anchor to scroll to
	var jqueryAnchor = $(id);
	var jQueryAnchorStripSubsection = $(sectionHash);

	// If the anchor exists
	if (jqueryAnchor != null && jqueryAnchor.length) {
		// Scroll to it
		gotoAnchor(jqueryAnchor);
	} else if (jQueryAnchorStripSubsection != null && jQueryAnchorStripSubsection.length){
		gotoAnchor(jQueryAnchorStripSubsection);
	} else {
		// Else show an error message
		showError();
	}
});

(function($){
	$.fn.extend({
		center: function (parent) {
			return this.each(function() {
				var left = (parent.width() - $(this).outerWidth()) / 2;

				$(this).css("margin", "0");

				if (left > 0) {
					$(this).css("left", left+'px');
				}
				else {
					$(this).css("left", '0px');
				}
			});
		}
	});
})(jQuery);

// HELPER FUNCTIONS

function gotoAnchor(anchor) {
	var reflexBoxHeight = $("#reflex2-notification-box").height();
	if (reflexBoxHeight == null) {
		// reflex box was hidden by the user, use default scroll
		anchor[0].scrollIntoView();
		return;
	}
	
	log("Going to anchor: " + anchor[0].outerHTML + ", " + reflexBoxHeight);
	var target_offset = anchor.offset();
	var target_top = target_offset.top - reflexBoxHeight - 50;
	var successActivated = false;
	$('html, body').animate(
			{
				scrollTop:target_top
			},
			'slow',
			function() {
				if (successActivated == false) {
				  successActivated = true;
				  showSuccess();
				}
			}
	);
}

function showSuccess() {
	hideStatusText();
}

function showError() {
	updateStatusText(" <span style=\"color: red\">" + REFLEX2_NOTIFICATION_I18N[language]["SECTION"] + " " + sectionLabel + " " + REFLEX2_NOTIFICATION_I18N[language]["NOT_FOUND"] + "</span>");
}

function hideNotificationBox(delay) {
	setTimeout(
			function() {hash.replace(/#(?:sec|art)(.+)_smooth/, function(match, section) {
	  	  targetText = REFLEX2_NOTIFICATION_I18N[language]["SECTION_LABEL"] + " " + section;
		  found = true;
		});
				$("#reflex2-notification-box").moveUp(400);
			},
			delay
	);
	updateAutoCloseDelay();
}

function updateStatusText(newText) {
	$("#reflex2-notification-box-search-status-label-only").fadeOut(
	  200,
	  function() {
	    $("#reflex2-notification-box-search-status-label-only").html(newText);
	    $("#reflex2-notification-box-search-status-label-only").fadeIn(200);
	  }
	);
}

function hideStatusText() {
	$("#reflex2-notification-box-search-status").fadeOut(200);
}

function log(string) {
	//if (console) {
	//	console.log(string);
	//}
}

(function($){
	$.fn.extend({
		moveUp: function (delay) {
			$(this).animate({
				top: "-" + $(this).outerHeight() + "px"
			}, delay);
		}
	});
    $.fn.extend({
		moveDown: function (delay) {
			$(this).animate({
				top: "0px"
			}, delay);
		}
	});
})(jQuery);

function capitaliseFirstLetter(string)
{
    return string.charAt(0).toUpperCase() + string.slice(1);
}

function updateDoc(params, newHash) {
    _params = params;
	var hash = (newHash == "" || newHash == null) ? document.location.hash : newHash;
	var found = false;

	if (DISABLED_JURISDICTIONS[params["jurisdiction"]] != null || isSmartphone()) {
	  return;
	}

	language = params["language"];

	// Check that we have a hash
	if (hash == "" || hash == null) {
		return;
	}

	// Parse the hash (extract section and subsection info)
	hash.replace(/#(?:sec|art)(.+)(?!para)(?:subsec|par)(.+)(?:para|al)(.+)_smooth/, function(match, section, subsection, alinea) {
	  let preAlinea = language == "en" ? "(" : " ";
	  sectionLabel = section + "(" + subsection + ")" + preAlinea + alinea + ")";
	  targetText = REFLEX2_NOTIFICATION_I18N[language]["SUBSECTION_LABEL"] + " " + section + "(" + subsection + ")" + preAlinea + alinea + ")";
	  found = true;
	});
	
	// If the previous parsing failed, then check for section and subsection
	if (found == false) {
	  hash.replace(/#(?:sec|art)(.+)(?!para)(?:subsec|par)(.+)_smooth/, function(match, section, subsection) {
	    sectionLabel = section + "(" + subsection + ")";
	    targetText = REFLEX2_NOTIFICATION_I18N[language]["SUBSECTION_LABEL"] + " " + section + "(" + subsection + ")";
	    found = true;
	  });
	}
	
	// If the previous parsing failed, then check for section and alinea
	if (found == false) {
	  hash.replace(/#(?:sec|art)(.+)(?:para|al)(.+)_smooth/, function(match, section, alinea) {
		let preAlinea = language == "en" ? "(" : " ";
	    sectionLabel = section + preAlinea + alinea + ")";
	    targetText = REFLEX2_NOTIFICATION_I18N[language]["SUBSECTION_LABEL"] + " " + section + preAlinea + alinea + ")";
	    found = true;
	  });
	}

	// If the previous parsing failed, then check only for section
	if (found == false) {
	  hash.replace(/#(?:sec|art)(.+)_smooth/, function(match, section) {
	    sectionLabel = section;
	    targetText = REFLEX2_NOTIFICATION_I18N[language]["SECTION_LABEL"] + " " + section;
	    found = true;
	  });
	}

	// If we did not detect any section number, then quit
	if (found == false) {
	  return;
	}

	// Update the delay in the notification box (invisible at first)
	$("#reflex2-notification-box-title").html(REFLEX2_NOTIFICATION_I18N[language]["TITLE"]);
	$("#reflex2-notification-box-title-label").text(REFLEX2_NOTIFICATION_I18N[language]["TITLE_LABEL"]  + ":");
	$("#reflex2-notification-box-citation-label").text(REFLEX2_NOTIFICATION_I18N[language]["CITATION_LABEL"] + ":");
	$("#reflex2-notification-box-location-label").text(REFLEX2_NOTIFICATION_I18N[language]["LOCATION_LABEL"] + ":");

	$("#reflex2-notification-box-jurisdiction-text").text(params["jurisdiction"]);
	$("#reflex2-notification-box-title-text").text(params["title"]);
	$("#reflex2-notification-box-citation-text").html(
	  params["citation"] +
	  ", " +
	  targetText +
	  "<div id=\"reflex2-notification-box-search-status-div\">" +
	    "<span id=\"reflex2-notification-box-search-status\"> - <span id=\"reflex2-notification-box-search-status-label-only\">" + REFLEX2_NOTIFICATION_I18N[language]["SEARCH_LABEL"] + "</span></span>" +
	  "</div>"
	);

	$("#reflex2-notification-box").show();

	$("#reflex2-notification-box").center($("#wrap"));
	$("#reflex2-notification-box").css("display", "block");
}
