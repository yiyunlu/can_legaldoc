function getTableOfContentsContent(legislationPartId, errorTabMsg) {
	let urlData = "/legislations/showToc?legislationPartId=" + legislationPartId;
	let longArticleCount = 0;

	enableSidebarLoading();

	function formatParagraphNumber(elt) {
		return (elt.paragraphNumber !== undefined ? " (" + elt.paragraphNumber + ")" : "");
	}

	function formatArticle(elt) {
		let article = (elt.type === "Heading") ? elt.label : elt.sectionNumber;
		let format = /^([IVXLC]+)(\.)([\s\S]*)?$/;
		let result = format.exec(article.trim());
		if (result) {
			return "<span class='article-number'>" + result[1] + "</span>" +
				"<span class='article-separator'>" + ((result[2] !== undefined) ? result[2] : "") + "</span>" +
				"<span class='article-paragraph'>" + formatParagraphNumber(elt) + "</span>";
		}
		format = /^(\w+)([\s.])([\w\W]+)?$/;
		result = format.exec(article.trim());
		if (result) {
			let text = "<span class='article-number'>";
			if (result[1].toLowerCase().indexOf("annex") === -1 && result[1].toLowerCase().indexOf("schedule") === -1 && result[1].toLowerCase().indexOf("form") === -1) {
				text += (result[1].toLowerCase() === "section") ? result[3] : result[1];
				text += "</span>";
				text += "<span class='article-separator'>";
				text += (result[2] !== undefined) ? result[2] : "";
				text += "</span>";
				text += "<span class='article-paragraph'>";
				text += (result[1].toLowerCase() !== "section" && result[3] !== undefined) ? result[3] : "";
				text += formatParagraphNumber(elt);
				text += "</span>";
			} else {
				text += result[1];
				text += "</span>";
				text += "<span class='article-separator'></span>";
				text += "<span class='article-paragraph'>" + formatParagraphNumber(elt) + "</span>";
			}
			if ((result[3]?.length + formatParagraphNumber(elt).length) > 8) {
				longArticleCount++;
			}
			return text;
		}
		return "<span class='article-number'>" + article + "</span><span class='article-separator'></span><span class='article-paragraph'>" + formatParagraphNumber(elt) + "</span>";
	}

	function formatLabel(elt) {
		if (elt.type === "SectionParagraph") {
			return ((elt.marginalNote !== undefined) ? elt.marginalNote
				: tableOfContentsLocales.section + elt.sectionNumber + formatParagraphNumber(elt));
		}
		return elt.label + (elt.title !== undefined ? " - " + elt.title : "")
	}

	function getAnchor(elt, isArticle) {
		let anchor;
		if (isArticle) {
			anchor = "<a class='article' href='#" + elt['anchor'] + "' " +
				"aria-label='" + ((elt.type === "Heading") ? elt.label : tableOfContentsLocales.section + elt.sectionNumber + formatParagraphNumber(elt)) + "'>" +
				formatArticle(elt) + "</a>";
		} else {
			anchor = "<div class='go-to'>" +
				"<a href='#" + elt['anchor'] + "'>" + formatLabel(elt) + "</a>" +
				"</div>";
		}
		return anchor;
	}

	function findFirstArticle(elt) {
		if (elt.type === 'Heading') {
			if (elt.subitems !== undefined && elt.subitems.length > 0) {
				return findFirstArticle(elt.subitems[0]);
			}
		}
		return getAnchor(elt, true);
	}

	function generateTableOfContents(data, depth) {
		let tableOfContents = "";
		data.forEach((elt) => {
			tableOfContents += "<li class='list-group-item'>";
			tableOfContents += "<div class='line'>";
			tableOfContents += findFirstArticle(elt);
			if (elt.subitems !== undefined && elt.subitems.length > 0) {
				tableOfContents += "<button type='button' class='btn toggle'" +
					" aria-label='" + tableOfContentsLocales.open + formatLabel(elt) + "'" +
					" data-label='" + formatLabel(elt) + "'" +
					" aria-expanded='false'>" +
					"<i class='fa-regular fa-caret-right'></i>" +
					"</button>";
			} else if (elt.type === "Heading" || elt.type === "SectionParagraph") {
				tableOfContents += "<span class='toggle invisible'></span>";
			}
			tableOfContents += getAnchor(elt, false);
			tableOfContents += "</div>";
			if (elt.subitems !== undefined && elt.subitems.length > 0) {
				tableOfContents += "<ol class='depth-" + depth + "'>" + generateTableOfContents(elt.subitems, depth + 1) + "</ol>";
			}
			tableOfContents += "</li>";
		});

		return tableOfContents;
	}

	$.getJSON(urlData, function (data) {
		let rootToc = $("#tableOfContentsTree .root-toc");
		rootToc.html(generateTableOfContents(data, 1));
		if (longArticleCount > ($("#tableOfContentsTree .root-toc li").length / 2)) {
			rootToc.addClass('long-articles');
		}
		if ($("#tableOfContentsLinkHover").length === 0) {
			$("#wrap").append("<div id='tableOfContentsLinkHover' class='bootstrap'></div>")
				.append("<div id='tableOfContentsArticleHover' class='bootstrap'></div>");
		}
	})
	.fail(function (jqXHR) {
		console.error(jqXHR);
		$("#errorTab").html(errorTabMsg).show();
	})
	.always(function () {
		disableSidebarLoading();
	});
}

function getCitedByTabContent(legislationId, lang, errorTabMsg) {
	let url = "/legislationTabs/citedBy/content?legislationId=" + legislationId + "&lang=" + lang;

	enableSidebarLoading();
	$.get(url, function (data) {
		$("#citedByTab").html(data);

		$('div.treatment-density .treatment-expand').on('click', function (e) {
			e.preventDefault();
			expandDensity();
			updateIframeHeight();
		});

		$('div.treatment-density .treatment-collapse').on('click', function (e) {
			e.preventDefault();
			compactDensity();
			updateIframeHeight();
		});

		$('div.citedBy .expand, div.citedBy .reduce').on('click', function (e) {
			toggleDensity(e);
			updateIframeHeight();
		});

		$('.show-more-link').on('click', function (e) {
			showMoreEnrichments(e);
		});

	})
	.fail(function (jqXHR) {
		console.error(jqXHR);
		$("#errorTab").html(errorTabMsg).show();
	})
	.always(function () {
		disableSidebarLoading();
	});
}

async function getSummaryTabContent(legislationId, legislationVersionId, lang, errorTabMsg, aiInfoTooltip) {
	let url = "/legislationTabs/summary/?legislationId=" + legislationId + "&legislationVersionId=" + legislationVersionId + "&lang=" + lang;

	try {
		enableSidebarLoading();

		const data = await $.get(url);
		$("#summaryTab").html(data);
		initSummaryClickEvent();
	} catch (jqXHR) {
		console.error(jqXHR);
		$("#errorTab").html(errorTabMsg).show();
	} finally {
		disableSidebarLoading();

		$("div.ai-content i.fa-info-circle").tooltip({
			placement : 'bottom',
			trigger : 'hover',
			title: aiInfoTooltip,
			container: '.canlii-sidebar.bootstrap',
			customClass: "bigger-tooltip"
		});

		$("#summary-tab-nav .nav-link").click(() => {
			updateIframeHeight();
		});

		manageSummaryHash();
	}
}

async function getHistoryTabContent(legislationId, legislationVersionId, lang, errorTabMsg) {
	let url = "/legislationTabs/versions/?legislationId=" + legislationId + "&legislationVersionId=" + legislationVersionId + "&lang=" + lang;

	try {
		enableSidebarLoading();

		const data = await $.get(url);
		$("#historyTab").html(data);
	} catch (jqXHR) {
		console.error(jqXHR);
		$("#errorTab").html(errorTabMsg).show();
	} finally {
		disableSidebarLoading();
	}
}

function displayRegulationsInSidebar() {
	$(".canlii-sidebar-content .sidebar-content > section").hide();
	$("#regulationsTab").show();
}

let tocExpandCollapseButton;
let tocLinkClicked = false;
let tocIsSearching;

function findParent(target, className) {
	let parent = $(target);
	while (!parent.hasClass(className)) {
		parent = parent.parent();
	}
	return parent;
}

$(document).on('click', '.go-to a, .article', (evt) => {
	evt.preventDefault();
	tocLinkClicked = true;
	let target = evt.target.tagName === "A" ? evt.target : $(evt.target).parent("a");
	$(".go-to a, .article").removeClass("active");
	$(target).addClass("active");
	smoothScrollTo($(target)[0].hash);
	return false;
})

function toggleBtn(btn, direction) {
	if (direction === "open") {
		btn.children("i").addClass("fa-caret-down").removeClass("fa-caret-right");
		btn.attr("aria-label", tableOfContentsLocales['close'] + btn.data("label"));
		btn.attr("aria-expanded", true);
	} else if (direction === "close") {
		btn.children("i").addClass("fa-caret-right").removeClass("fa-caret-down");
		btn.attr("aria-label", tableOfContentsLocales['open'] + btn.data("label"));
		btn.attr("aria-expanded", false);
	}
}

function toggleSubitems(parent, forceOpen) {
	if (forceOpen) {
		parent.children(".line").children(".article").addClass("invisible");
		toggleBtn(parent.children(".line").children(".toggle"), "open");
		parent.children("ol").children("li").show();
	} else if (parent.children("ol").children("li").is(":visible")) {
		parent.children(".line").children(".article").removeClass("invisible");
		toggleBtn(parent.children(".line").children(".toggle"), "close");
		parent.children("ol").children("li").hide();
	} else {
		toggleBtn(parent.children(".line").children(".toggle"), "open");
		parent.children("ol").children("li").slideDown(300);
		if (!parent.children(".line").children(".toggle").hasClass("invisible")) {
			parent.children(".line").children(".article").addClass("invisible");
		}
	}
}

$(document).on('click', '#tableOfContentsTree .line .go-to, #tableOfContentsTree .line .toggle', (evt) => {
	evt.preventDefault();
	toggleSubitems(findParent(evt.target, "list-group-item"), false);
	updateIframeHeight(325);
	return false;
})

$(document).on('click', '#tableOfContentsExpandCollapse', (evt) => {
	evt.preventDefault();
	$("#tableOfContentsItemsFilter input").val("");
	$("#tableOfContentsTree .line a").removeClass("active");

	toggleSubitems($("#tableOfContentsTree .list-group-item"), tocExpandCollapseButton.hasClass("collapsed"));
	if (tocExpandCollapseButton.hasClass("collapsed")) {
		$("#tableOfContentsExpandCollapse i").removeClass("fa-arrows-from-line").addClass("fa-arrows-to-line");
		tocExpandCollapseButton.attr("aria-expanded", true)
			.attr("aria-label", tableOfContentsLocales['collapse'])
			.removeClass("collapsed");
		$(".toggle.invisible").siblings(".article").removeClass("invisible");
	} else {
		$("#tableOfContentsExpandCollapse i").removeClass("fa-arrows-to-line").addClass("fa-arrows-from-line");
		tocExpandCollapseButton.attr("aria-expanded", false)
			.attr("aria-label", tableOfContentsLocales['expand'])
			.addClass("collapsed");
	}
	tocExpandCollapseButton.tooltip('dispose').attr("title", tocExpandCollapseButton.attr("aria-label"));
	tocExpandCollapseButton.tooltip('show');
	updateIframeHeight();
	return false;
})

$(document).on('keyup', '#tableOfContentsItemsFilter input', (evt) => {
	evt.preventDefault();
	if (evt.keyCode === 13) {
		$("#tableOfContentsItemsFilter button").trigger("click");
	} else if ($(evt.target).val().trim().length > 3) {
		if (!isNaN(tocIsSearching)) {
			clearTimeout(tocIsSearching);
		}
		tocIsSearching = setTimeout(() => {
			$("#tableOfContentsItemsFilter button").trigger("click");
		}, 300);
	}
});

$(document).on('click', '#tableOfContentsItemsFilter button', (evt) => {
	evt.preventDefault();

	function showParents(elt) {
		let p = $(elt).parent().parent("ol");
		if (p.length > 0) {
			p.parent().show();
			showParents(p);
		}
	}

	let found = false;
	let text = $("#tableOfContentsItemsFilter input").val().trim().toLowerCase();
	$("#tableOfContentsTree .line a").removeClass("active");

	if (text.length > 0) {
		toggleSubitems($("#tableOfContentsTree .list-group-item"), true);
		$("#tableOfContentsTree .go-to a").toArray().forEach((elt) => {
			let textLink = $(elt).text().trim().toLowerCase();
			let foundLink = textLink.indexOf(text) !== -1;
			let line = findParent(elt, "line");
			let textArticle = line.children(".article").text().trim().toLowerCase();
			let foundArticle = textArticle.indexOf(text) !== -1;
			if (foundLink || foundArticle) {
				found = true;
				if (foundArticle) {
					line.children(".article").addClass("active");
				}
				if (foundLink) {
					$(elt).addClass("active");
				}
				line.children(".article").removeClass("invisible");
				showParents(line);
			} else {
				if (!line.parent().parent().hasClass("depth-0")) {
					line.parent().hide();
				}
			}
			toggleBtn(line.children(".toggle"), "close");
		});
		if (!found) {
			toggleSubitems($("#tableOfContentsTree .list-group-item"), true);
			toggleSubitems($("#tableOfContentsTree .list-group-item"), false);
			$("#tableOfContentsItemsFilter, #tableOfContentsItemsFilter input").addClass("is-invalid");
		} else {
			$("#tableOfContentsItemsFilter, #tableOfContentsItemsFilter input").removeClass("is-invalid");
			$(".toggle.invisible").siblings(".article").removeClass("invisible");
		}
	}
})

$(document).on('input', '#tableOfContentsItemsFilter input', (evt) => {
	if (evt.target.value.length === 0) {
		$("#tableOfContentsTree .line a").removeClass("active");
		toggleSubitems($("#tableOfContentsTree .list-group-item"), true);
		toggleSubitems($("#tableOfContentsTree .list-group-item"), false);
		$("#tableOfContentsItemsFilter, #tableOfContentsItemsFilter input").removeClass("is-invalid");
		$(".toggle.invisible").siblings(".article").removeClass("invisible");
	}
})

$(document).on('mouseenter', '#tableOfContentsTree .line', (evt) => {
	let target = findParent(evt.target, "line");
	let link = $(target).children(".go-to");
	let article = $(target).children(".article");
	$("#tableOfContentsLinkHover").css({
		display: "block",
		left: Math.round(link.offset().left - $(window).scrollLeft()) - 1,
		top: Math.round(link.offset().top - $(window).scrollTop())
	});
	$("#tableOfContentsLinkHover").text(link.text());
	$("#tableOfContentsArticleHover").css({
		display: "block",
		left: Math.round(article.offset().left - $(window).scrollLeft()) - 1,
		top: Math.round(article.offset().top - $(window).scrollTop())
	});
	$("#tableOfContentsArticleHover").html(article.html());
})

$(document).on('mouseleave', '#tableOfContentsTree', () => {
	$("#tableOfContentsArticleHover, #tableOfContentsLinkHover").css({"display": "none"});
})

$(document).ready(() => {
	$('.canlii-sidebar').scroll(() => {
		$("#tableOfContentsArticleHover, #tableOfContentsLinkHover").css({"display": "none"});
	})
	$(document).scroll(() => {
		if (!tocLinkClicked && $("#tableOfContentsItemsFilter input").val().length === 0) {
			$("#tableOfContentsTree .active").removeClass("active");
		}
	})
	tocExpandCollapseButton = $("#tableOfContentsExpandCollapse");
	tocExpandCollapseButton.tooltip({
		title: tocExpandCollapseButton.attr("aria-label"),
	});
})
