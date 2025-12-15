var canliiCustomNavBar = {
    /**
     * Sera appelé une fois lorsque le surligneur sera prêt à afficher la barre.
     *
     * options: un objet identique à l'argument "options" qui est passé à la fonction d'initialisation du surligneur.
     * highlighter: un objet permettant à la barre d'interagir avec le surligneur (voir plus bas.)
     */
    init: function(options, highlighter) {
		_highlight.highlighter = highlighter;
    	var highlightMatch = options.highlightMatch;
    
		for (var i=0; i<options.terms.length; i++) {
			if (options.terms[i].isPresentInDocument == true || !highlightMatch) {
				_highlight.atLeastOneTerm = true;
				break;
			}
		}
	
		var edited = options.edited;
		var hasHeader = options.hasHeader;
		var pdfMode = options.pdfMode;
		var pdfFirstPage = options.pdfFirstPage || 1;
		var pdfTotalPages = options.pdfTotalPages || 0;

		let lang = getLanguage();
		var highlightbarPageLabel = "Page";
		var highlightbarOf = lang === "fr" ? "de" : "of";
		var highlightbarEditTip = lang === "fr" ? "Modifier votre requête pour ce document." : "Change your query for the current document.";
		var highlightbarPreviousTip = lang === "fr" ? "Occurence précédente" : "Previous appearance";
		var highlightbarNextTip = lang === "fr" ? "Occurence suivante" : "Next appearance";
		var hiPlaceholder = lang === "fr" ? "Trouver dans le document" : "Find in document";
		var highlightbarSearchTip = lang === "fr" ? "Rechercher dans le document" : "Search within the document";
		var highlightbarCancelTip = lang === "fr" ? "Annuler la modification" : "Cancel";

		// bar should be hidden by default if not on the document tab
		let defaultDisplay = "d-flex";
		// if (!$("div#documentContent").hasClass("active")) {
		// 	defaultDisplay = "d-none";
		// }

    	var hiBar = 
			'<div id="hiBar" class="bootstrap d-print-none ' + defaultDisplay + ' ' + (hasHeader == false ? 'framed' : '') + '">' +
            	'<div id="hiBar-body" class="d-flex">' +
            		'<div id="hiBar-page-widget" class="control-text ' + (pdfMode == true ? 'd-flex' : 'd-none') + '">' +
            			'<label for="hiBar-page-widget-page-number-input" id="hiBar-page-widget-label">' + highlightbarPageLabel + '</label>' +
            			'<input id="hiBar-page-widget-page-number-input" class="form-control form-control-sm" type="text" value="' + pdfFirstPage + '">' +
            			'<span>&nbsp;</span>' +
            		'</div>' +
            		'<div id="hiBar-highlight-widget-search" class="d-flex">' +
            			'<div id="hiBar-highlight-widget-search-terms-edit" class="' + (_highlight.atLeastOneTerm == false ? 'd-flex' : 'd-none') + '">' +
							'<div class="input-group input-group-sm">' +
								'<button id="hiBar-highlight-widget-search-terms-edit-ok" title="' + highlightbarSearchTip + '" class="btn" type="button"><i class="far fa-search"></i></button>' +
								'<input id="hiBar-highlight-widget-search-terms-edit-input" class="form-control" type="search" aria-label="' + hiPlaceholder + '" placeholder="' + hiPlaceholder + '">' +
							'</div>' +
							'<button id="hiBar-highlight-widget-search-terms-edit-cancel" ' + (_highlight.atLeastOneTerm == false ? 'class="d-none"' : '') + ' title="' + highlightbarCancelTip + '"><i class="fas fa-times"></i></button>' +
            			'</div>' +
            			'<div id="hiBar-highlight-widget-search-terms-container" class="' + (_highlight.atLeastOneTerm == false ? 'd-none' : 'd-flex') + '">' +
            				'<div id="hiBar-highlight-widget-search-terms" class="d-flex"></div>' +
            				'<div id="hiBar-highlight-widget-counts" class="control-text d-flex">' +
            					'<span id="highlight-count">0</span>' +
            					'<span>&nbsp;</span>' +
            					'<span>' + highlightbarOf + '</span>' +
            					'<span>&nbsp;</span>' +
            					'<span id="highlight-total-count">0</span>' +
            				'</div>' +
            				'<div id="hiBar-highlight-widget-search-controls" class="d-flex">' +
            					'<button id="hiBar-highlight-widget-prev" title="' + highlightbarPreviousTip + '"><i class="fas fa-caret-up"></i></button>' +
            					'<button id="hiBar-highlight-widget-next" title="' + highlightbarNextTip + '"><i class="fas fa-caret-down"></i></button>' +
            					'<button id="hiBar-highlight-widget-edit" title="' + highlightbarEditTip + '"><i class="fa-solid fa-pen-to-square"></i></button>' +
            				'</div>' +
            			'</div>' +
            		'</div>' +
            	'</div>' +
            '</div>';

		if (hasHeader == true) {
			if (_highlight.atLeastOneTerm) {
				$("#canlii-header .bottom-bar").empty().append($(hiBar));
				$("#canlii-header .bottom-bar").css("display", "flex");
			}
		} else {
			// this means we are on the search page
			_highlight.scrollDocument = parent.document;
			_highlight.scrollWindow = parent.window.$(".search-pane");

			var highlightBar = $("#hiBar", _highlight.scrollDocument);
			if (highlightBar == null || highlightBar.length == 0) {
				$("#hiBarContainer", _highlight.scrollDocument).append(hiBar);
			} else {
				highlightBar[0].outerHTML = hiBar;
			}
		}

		highlighter.setActiveTerms(options.terms);
		_highlight.activeTerms = options.terms;
		_highlight.createTermsCheckboxes(options.terms, highlightMatch, highlighter);

		$("#hiBar-highlight-widget-prev", _highlight.scrollDocument).click(function() {
			_highlight.scrollPrev(true);
		});
		$("#hiBar-highlight-widget-next", _highlight.scrollDocument).click(function() {
			_highlight.scrollNext(true);
		});
		$("#hiBar-highlight-widget-edit", _highlight.scrollDocument).click(_highlight.editHighlight);
		$("#hiBar-highlight-widget-search-terms-edit-cancel", _highlight.scrollDocument).click(_highlight.cancelEditHighlight);
		$("#hiBar-highlight-widget-search-terms-edit-ok", _highlight.scrollDocument).click(function () {
            _highlight.submitNewHighlight();
        });
		$("#hiBar-highlight-widget-search-terms-edit-input", _highlight.scrollDocument).on("keyup", _highlight.handleKeyPressed);
		$("#hiBar-page-widget-page-number-input", _highlight.scrollDocument).keyup(function(e) {
            if (e.keyCode === 13) {
                _highlight.scrollToPage(hasHeader, pdfFirstPage, pdfTotalPages);
            }
        });

		if (pdfMode == true) {
			$(_highlight.scrollWindow).scroll(function() {
			    _highlight.updatePageInput(pdfFirstPage);
			});
		}
		
		let highlightbarMissingTermTip = lang === "fr" ? "Ce terme n'a pas été trouvé dans ce document, Cependant, les termes de votre requête se trouvent très fréquemment dans les documents qui citent ce document, ce qui est considéré par le moteur de recherche comme un indice clair de pertinence."
			 : "This term could not be found in the current document. However, your query appears disproportionally often in documents citing this document, which is considered by the search engine a strong indication of relevance.";
		if (edited == true) {
			highlightbarMissingTermTip = lang === "fr" ? "Ce terme n'a pas été trouvé dans ce document."
			 : "This term could not be found in the document.";
		}

		$(".solexMissingTermIcon", parent.document).tooltip({
			placement : 'bottom',
			trigger : 'hover',
			html: true,
			title: highlightbarMissingTermTip,
			container: $(".solexMissingTermIcon", parent.document).closest('.bootstrap')
		});

		if (edited == false && $(".solexMissingTermIcon", parent.document).length > 0) {
			CanliiAnalytics.searchResultMissingCitNetTerms();
		}
	},

    /**
     * Appelé par le surligneur pour indiquer quel terme est présentement sélectionné (ex: 1 of 128). Cette fonction
     * sera appelée:
     *  1. Immédiatement après l'initialisation;
     *  2. Lorsque l'usager scroll la page manuellement et que le terme sélectionné change;
     *  3. Après un appel à callback.scrollNext/scrollPrevious;
     *  3. Lorsque l'usager active ou désactive certains termes (normalement après un appel à highlighter.setActiveTerms).
     *
     * currentTermIndex: l'index du terme/phrase présentement sélectionné (0 à l'initialisation, indexé à 1)
     * termCount: le nombre de termes/phrases surlignés sur la page.
     */
    setCurrentTermIndex: function(currentTermIndex, termCount) {
		$("#highlight-count", _highlight.scrollDocument).text(currentTermIndex);
		$("#highlight-total-count", _highlight.scrollDocument).text(termCount);

		if (_highlight.getCurrentTermsCount() === 0 && _highlight.getTotalTermsCount() === 0) {
			this.disableButton("#hiBar-highlight-widget-prev");
			this.disableButton("#hiBar-highlight-widget-next");
		} else if (_highlight.getCurrentTermsCount() === 1) {
			if (_highlight.getTotalTermsCount() === 1) {
				// au cas ou l'usager scroll et veut revenir au seul résultat, on garde les boutons actifs
				this.enableButton("#hiBar-highlight-widget-prev");
				this.enableButton("#hiBar-highlight-widget-next");
			} else {
				this.disableButton("#hiBar-highlight-widget-prev");
				this.enableButton("#hiBar-highlight-widget-next");
			}
		} else if (_highlight.getCurrentTermsCount() === _highlight.getTotalTermsCount()) {
			this.enableButton("#hiBar-highlight-widget-prev");
			this.disableButton("#hiBar-highlight-widget-next");
		} else {
			this.enableButton("#hiBar-highlight-widget-prev");
			this.enableButton("#hiBar-highlight-widget-next");
		}
	},

	enableButton: function (buttonId) {
		$(buttonId, _highlight.scrollDocument).attr("tabindex", "0");
		$(buttonId, _highlight.scrollDocument).removeClass("disabled");
	},

	disableButton: function (buttonId) {
		$(buttonId, _highlight.scrollDocument).attr("tabindex", "-1");
		$(buttonId, _highlight.scrollDocument).addClass("disabled");
	},
}

var _highlight = {
	highlighter: null,
	scrollDocument: document,
	scrollWindow: window,
    atLeastOneTerm: false,
    originalSearchText: "",
    activeTerms: [],

	scrollPrev: function(buttonClicked) {
		if (this.highlighter != null) {
			this.highlighter.scrollPrevious();
			if (buttonClicked != undefined && buttonClicked == true) {
				CanliiAnalytics.highlightScroll(_highlight.getCurrentTermsCount(), _highlight.getTotalTermsCount(), "previous");
			}
		}
	},

	scrollNext: function(buttonClicked) {
		if (this.highlighter != null) {
			this.highlighter.scrollNext();
			if (buttonClicked != undefined && buttonClicked == true) {
				CanliiAnalytics.highlightScroll(this.getCurrentTermsCount(), this.getTotalTermsCount(), "next");
			}
		}
	},

	editHighlight: function() {
        const params = new URLSearchParams(window.location.search);
        const searchUrlHash = params.get("searchUrlHash");
        
		$.ajax({
	        url: "/search/parseSearchUrlHash",
	        data: {
	            hash: searchUrlHash
	        },
	        timeout: 2000,
	        success: function(data) {
	            var queries = [];
	
	            var texts = data.text;
	            if (texts) {
	                for (var i = 0; i < texts.length; i++) {
	                    queries.push(texts[i]);
	                }
	            }
	
	            var noteups = data.noteups;
	            if (noteups) {
	                for (var i = 0; i < noteups.length; i++) {
	                    queries.push('"' + noteups[i].display + '"');
	                }
	            }
	
	            $("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-edit-input", _highlight.scrollDocument).val(queries.join(" "));
	            _highlight.displayNone($("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-container", _highlight.scrollDocument));
	            _highlight.displayFlex($("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-edit", _highlight.scrollDocument));
	
	            _highlight.originalSearchText = queries.join(" ");
	            
	            $("#hiBar-highlight-widget-search-terms-edit-input", _highlight.scrollDocument).off("keyup");
	            $("#hiBar-highlight-widget-search-terms-edit-input", _highlight.scrollDocument).focus();
	            
	            setTimeout(function () {
					// need to give some time, so the keyup from the focus is not triggered
					$("#hiBar-highlight-widget-search-terms-edit-input", _highlight.scrollDocument).on("keyup", _highlight.handleKeyPressed);
				}, 500);
	        },
	        error: function() {
	            _highlight.displayFlex($("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-container", _highlight.scrollDocument));
	            _highlight.displayNone($("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-edit", _highlight.scrollDocument));
	        }
	    });
	},
	
	submitNewHighlight: function() {
	    this.highlightFromInput("#hiBar-highlight-widget-search-terms-edit-input");
	},

	highlightFromInput: function(inputSelector) {
		if (_highlight.originalSearchText === $(inputSelector, _highlight.scrollDocument).val()) {
			if (_highlight.atLeastOneTerm == true) {
				_highlight.displayFlex($("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-container", _highlight.scrollDocument));
				_highlight.displayNone($("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-edit", _highlight.scrollDocument));
			}
			return;
		}

		$(inputSelector, _highlight.scrollDocument).prop('disabled', true);
		$.ajax({
			url: "/search/getSearchUrlHash",
			data: {
				query: $(inputSelector, _highlight.scrollDocument).val()
			},
			timeout: 2000,
			success: function(data) {
				const offset = $(document).scrollTop();
                const urlObj = new URL(window.location.href);

                urlObj.searchParams.set("searchUrlHash", data);
                urlObj.searchParams.set("offset", offset);
                urlObj.searchParams.set("highlightEdited", "true");

                window.location.href =  urlObj.toString();
			},
			error: function() {
				$(inputSelector, _highlight.scrollDocument).prop('disabled', false);
				_highlight.displayFlex($("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-container", _highlight.scrollDocument));
				_highlight.displayNone($("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-edit", _highlight.scrollDocument));
			}
		});
	},
	
	cancelEditHighlight: function() {
		_highlight.displayFlex($("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-container", _highlight.scrollDocument));
	    _highlight.displayNone($("#hiBar", _highlight.scrollDocument).find("#hiBar-highlight-widget-search-terms-edit", _highlight.scrollDocument));
	},
	
	handleKeyPressed: function(e) {
		if (e.which === 13) {
            _highlight.submitNewHighlight();
        } else if (e.which === 27) {
            _highlight.cancelEditHighlight();
        }
	},
	
	createTermsCheckboxes: function(terms, highlightMatch, highlighter) {
		$.each(terms, function(i, term) {
	        if (!term.isPresentInDocument && highlightMatch) {
	            return true;
	        }
	
			let labelDomElement = null;
			if (term.isPresentInDocument) {
				// default label
				let termId = term.cssClass.substring(term.cssClass.indexOf('T') + 1);
				
		        labelDomElement = $(
		            "<label id='solexTerm" + termId + "' " +
		                   "class='lexumSolrTermLabel lexumSolrTermInBar " + term.cssClass + "' " +
		                   "for='lexumSolrCheck" + termId + "' >" +
		            "<input id='lexumSolrCheck" + termId + "' " +
		                    "type='checkbox' " +
		                    "termid='" + termId + "' termindex='" + i + "' />" + term.label +
		            "</label>");
		            
		        var checkedInput = $(labelDomElement).find("input");
		        // check the box if highlight is ON
		        if (_highlight.activeTerms[i]) {
		            checkedInput.prop("checked", true);
		        }
		        else {
		            labelDomElement.addClass("solexNohl");
		        }
		
		        // Handle checkbox change listener (check uncheck)
		        $(checkedInput).on("change", function() {
		            _highlight.labelChanged(checkedInput, highlighter);
		        });
	        
	        	// could not find a way to disable stopwords by default, so we trigger a change manually
		        if (term.isStopWord) {
		        	labelDomElement.addClass("solexNohl");
					checkedInput.prop("checked", false).change();
				}
			} else {
				// missing term label without input
				labelDomElement = $(
	            "<label class='lexumSolrTermLabel lexumSolrTermInBar solexMissingTerm'>" + term.label +
	                   "<sup><span><i aria-hidden='true' class='far fa-question-circle solexMissingTermIcon'></i></span></sup>" +
	            "</label>");
			}
	
	        $("#hiBar-highlight-widget-search-terms", _highlight.scrollDocument).append(labelDomElement);
	    });
	},
	
	labelChanged: function (checkedInput, highlighter) {
		let termId = checkedInput.attr("termid");
		let termIndex = checkedInput.attr("termindex");
		
		let active = _highlight.isChecked(checkedInput);
	    _highlight.activeTerms[termIndex] = active;
		let label = $("#solexTerm"+termId, _highlight.scrollDocument);
		let termsInDocument = $(".solexT"+termId);
		if (active) {
			label.removeClass("solexNohl");
			termsInDocument.removeClass("solexNohl");
		}
		else {
			label.addClass("solexNohl");
			termsInDocument.addClass("solexNohl");
		}
	
	    highlighter.setActiveTerms(_highlight.activeTerms);
	    
	    // do not send analytics if this function was triggered by a stopwork initialization
	    if (label.length > 0) {
		    CanliiAnalytics.highlightTermClicked(label.text(), active);
		} 
	},
	
	isChecked: function(checkbox) {
		if (checkbox === undefined) {
	        // The term is not in the document
	        return false;
	    }
	    return checkbox.is(":checked");
	},
	
	displayFlex: function(element) {
		element.addClass("d-flex");
    	element.removeClass("d-none");
	},
	
	displayNone: function(element) {
		element.removeClass("d-flex");
    	element.addClass("d-none");
	},
	
	scrollToPage: function(hasHeader, firstPage, totalPages) {
		let firstDataPageValue = $(".pdf-viewer-page").first().data("page"); // can start at 0 or 1
		let hiBarPageInput = $("#hiBar-page-widget-page-number-input", _highlight.scrollDocument);
        let targetPage = hiBarPageInput.val();

		let dataPageToScroll = null;
        if (!targetPage || targetPage < firstPage) {
			targetPage = firstPage;
            dataPageToScroll = firstDataPageValue;
        }
        else if (targetPage > firstPage + totalPages) {
			targetPage = firstPage + totalPages -1;
            dataPageToScroll = firstDataPageValue + totalPages - 1;
        } else {
			dataPageToScroll = targetPage - firstPage + firstDataPageValue;
		}

        hiBarPageInput.val(targetPage);
		
		let elementToScroll = $(".pdf-viewer-page[data-page=" +  dataPageToScroll + "]");
		if (elementToScroll != null && elementToScroll.length > 0) {
			let scrollPos = elementToScroll.offset().top;
			if (hasHeader == true) {
				scrollPos = scrollPos - $("#canlii-header").height();
				$("html").animate({ scrollTop: scrollPos }, 'slow');
			} else {
				scrollPos = scrollPos + $("#searchDocumentFrame", _highlight.scrollDocument).offset().top - $("#canlii-header", _highlight.scrollDocument).height() - $("#framedTopBar", _highlight.scrollDocument).outerHeight(true);
				$(_highlight.scrollWindow).animate({ scrollTop: scrollPos }, 'slow');
			}
			
		}
	},
	
	updatePageInput: function(firstPage) {
		let textLayers = $(".pdf-viewer-page:above-the-middle(.search-pane)");

        if (textLayers && textLayers[0]) {
            let pageNumber = parseInt(textLayers[0].getAttribute("data-page"));
			let firstDataPageValue = $(".pdf-viewer-page").first().data("page"); // can start at 0 or 1
			let potentialNextPage = pageNumber + firstPage - firstDataPageValue;
			if (potentialNextPage >= firstPage) {
				$("#hiBar-page-widget-page-number-input", _highlight.scrollDocument).val(potentialNextPage);
			}
        }
	},
	
	getCurrentTermsCount: function() {
		const id = "#highlight-count";
		var value =  $(id).text();
		if(value){
			return parseInt(value);
		}else{
			return parseInt(window.parent.$(id).text());
		}
	},
	
	getTotalTermsCount: function() {
		const id = "#highlight-total-count";
		var value =  $(id).text();
		if(value){
			return parseInt(value);
		}else{
			return parseInt(window.parent.$(id).text());
		}
	},
};
