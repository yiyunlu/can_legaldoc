let sidebarDefaultSize = getSidebarDefaultWidth();
let sidebarSizeWhenOpen = sidebarDefaultSize;

function getSidebarDefaultWidth() {
    const temp = document.createElement('div');
    temp.style.cssText = `
        position: absolute;
        visibility: hidden;
        height: 0;
        width: var(--sidebar-default-open-width);
    `;
    document.documentElement.appendChild(temp);

    const computedWidth = getComputedStyle(temp).width;
    document.documentElement.removeChild(temp);
    return computedWidth;
}

function initToolbarAndSidebar() {
    manageResizes();
    initResizableSidebar();
    addToolbarEvents();
}

function addToolbarEvents() {
    $('.toolbar .mobile-button-left').on("click", function (evt) {
        evt.preventDefault();
        $('.toolbar .toolbar-menu').animate({
            scrollLeft: '-=150px'
        }, 'slow');
    });
    $('.toolbar .mobile-button-right').on("click", function (evt) {
        evt.preventDefault();
        $('.toolbar .toolbar-menu').animate({
            scrollLeft: '+=150px'
        }, 'slow');
    });
    $('.toolbar .toolbar-menu').on('scroll', function (evt) {
        if ($(this).scrollLeft() === 0) {
            $('.toolbar .mobile-button-left').addClass('d-none disabled');
        } else {
            $('.toolbar .mobile-button-left').removeClass('d-none disabled');
        }
        if ($(this).scrollLeft() === (evt.target.scrollWidth - evt.target.clientWidth)) {
            $('.toolbar .mobile-button-right').addClass('d-none disabled');
        } else {
            $('.toolbar .mobile-button-right').removeClass('d-none disabled');
        }
    })
    $(document).on('click', '.toolbar .toolbar-menu-item:not(.disabled)', function (evt) {
        evt.preventDefault();
        _paq.push(['trackEvent', "Boutons de la barre d'outils", 'clic', $(this).attr('id')]);
    });
    $(document).on('click', '.canlii-sidebar .canlii-sidebar-content .summary-parag-link', function (evt) {
        evt.preventDefault();
        _paq.push(['trackEvent', 'Liens dans les résumés', 'clic', $.trim($(this).text())]);
    });
    $(document).on('click', '.canlii-sidebar .canlii-sidebar-content .nav-link', function (evt) {
        evt.preventDefault();
        _paq.push(['trackEvent', 'Boutons de traduction des résumés', 'clic', $(this).attr('id') + ":" + $.trim($(this).text())]);
    });

}

function manageResizes() {
    // header resizes when highlighting
    if (document.querySelector("#canlii-header")) {
        const resizeObserver = new ResizeObserver(reflowComponents);
        resizeObserver.observe(document.querySelector("#canlii-header"));

        window.addEventListener("resize", reflowComponents);
    }
}

function reflowComponents() {
    const headerFullHeight = document.querySelector("#canlii-header").getBoundingClientRect().height;

    const toolbar = document.querySelector(".toolbar");
    toolbar.style.top = headerFullHeight + "px";
    toolbar.style.height = (window.innerHeight - headerFullHeight) + "px";

    const sidebar = document.querySelector(".canlii-sidebar");
    if (isSmallScreenOrReadingPane()) {
        sidebar.style.height = "auto";
        sidebar.style.width = "auto";
    } else {
        sidebar.style.top = headerFullHeight + "px";
        sidebar.style.height = (window.innerHeight - headerFullHeight) + "px";
        if (sidebar.classList.contains("cs-open")) {
            sidebar.style.width = sidebarSizeWhenOpen;

            const resizer = document.querySelector(".flex-resizer");
            resizer.style.display = "block";
        }
    }

    const heatmap = document.querySelector(".heatmap");
    heatmap.style.top = headerFullHeight + "px";
    heatmap.style.height = (window.innerHeight - headerFullHeight) + "px";

    const toolbarMenu = document.querySelector(".toolbar .toolbar-menu");
    if (toolbarMenu.scrollWidth > toolbarMenu.clientWidth) {
        $('.toolbar .mobile-button-right').removeClass('d-none disabled');
    } else {
        $('.toolbar .mobile-button').addClass('d-none disabled');
    }
}

function initResizableSidebar() {
    const sidebar = document.querySelector(".canlii-sidebar");
    const resizer = document.querySelector(".flex-resizer");
    const minSize = 0;

    let originalWidth = 0;
    let originalMouseX = 0;
    resizer.addEventListener("mousedown", function(e) {
        e.preventDefault();
        sidebar.classList.add("no-transition");
        originalWidth = parseFloat(getComputedStyle(sidebar, null).getPropertyValue("width").replace("px", ""));
        originalMouseX = e.pageX;
        window.addEventListener("mousemove", resize)
        window.addEventListener("mouseup", stopResize)
    });

    function resize(e) {
        const width = originalWidth + (e.pageX - originalMouseX);
        if (width > minSize) {
            let newWidth = width + 'px';
            sidebar.style.width = newWidth;
            sidebarSizeWhenOpen = newWidth;
        }
    }

    function stopResize() {
        window.removeEventListener("mousemove", resize);
        sidebar.classList.remove("no-transition");
        if (parseInt(sidebar.style.width, 10) < 15) {
            closeSidebar();
        }
    }

    let sidebarToggler = $("div.canlii-sidebar-toggler button");
    sidebarToggler.tooltip({
        placement: 'bottom',
        trigger: 'hover',
        title: sidebarToggler.attr("aria-label"),
        container: 'footer.bootstrap'
    });
}

function enableTriggerIfNecessary(url, idPrefix) {
    $.get(url, function(data) {
        if (data == true) {
            enableTrigger(idPrefix);
            if (idPrefix === "ai") {
                showCount(idPrefix, newMsg);
            }
        }
    })
    .fail(function(jqXHR) {
        console.error(jqXHR);
    })
    .always(function() {
    });
}

function enableTrigger(idPrefix) {
    $("#" + idPrefix + "-trigger").attr("tabindex", "0");
    $("#" + idPrefix + "-trigger").removeClass("disabled");
}

function loadToolbarButtonCount(url, idPrefix, noDisable) {
    $.get(url, function(data) {
        if (data != "0" || (noDisable != undefined && noDisable == true)) {
            enableTrigger(idPrefix);
            showCount(idPrefix, data);
        }
    })
    .fail(function(jqXHR) {
        console.error(jqXHR);
        $("#" + idPrefix + "-trigger .toolbar-menu-item-count span").html("?");
    })
    .always(function() {
        $("#" + idPrefix + "-spinner").hide("fast");
    });
}

function showCount(idPrefix, data) {
    $("#" + idPrefix + "-trigger .toolbar-menu-item-count").css("display", "flex");
    $("#" + idPrefix + "-trigger .toolbar-menu-item-count span").html(data);
}

function openSidebar() {
    $(".canlii-sidebar").css("display", "block");
    $(".canlii-sidebar").addClass("cs-open");

    if (!isSmallScreenOrReadingPane()) {
        $(".canlii-sidebar").css("width", getSidebarDefaultWidth());
        $(".flex-resizer").show();
    }
}

function closeSidebar() {
    $(".toolbar-menu-item").removeClass("selected");
    $(".canlii-sidebar").removeClass("cs-open");
    if ($(".canlii-sidebar-content .sidebar-content").length === 0) {
        $(".canlii-sidebar-content").empty();
    } else {
        $(".canlii-sidebar-content .sidebar-content > section").hide();
    }

    if (!isSmallScreenOrReadingPane()) {
        $(".canlii-sidebar").css("width", "0px");
        sidebarSizeWhenOpen = sidebarDefaultSize;

        $(".flex-resizer").hide();
    }

    updateIframeHeight();

    // sidebar must not be displayed when closed to prevent TAB navigation from going inside
    $(".canlii-sidebar").css("display", "none");
}

function enableSidebarLoading() {
    $(".canlii-sidebar-content").addClass("loading");
    $(".canlii-sidebar-loader").show();
}

function disableSidebarLoading() {
    $(".canlii-sidebar-loader").hide();
    $(".canlii-sidebar-content").removeClass("loading");
    updateIframeHeight();
}

function isSmallScreenOrReadingPane() {
    // ipad pro or smaller or reading pane
    let documentsFrame = parent.document.querySelector("#searchDocumentFrame");
    if (documentsFrame != null) {
        return true;
    }

    if ($(".toolbar").css("position") == "static") {
        return true;
    }
    return false;
}

function toggleDensity(event) {
    event.preventDefault();

    var closestLi = $(event.currentTarget).closest("li");

    if (closestLi.hasClass("compact")) {
        closestLi.removeClass("compact");
        closestLi.addClass("full");
    } else {
        closestLi.removeClass("full");
        closestLi.addClass("compact");
    }
}

function expandDensity() {
    $("li.result").removeClass("compact");
    $("li.result").removeClass("full");

    $("div.treatment-density button img").attr("src", "/images/icons/expanded-results.svg")
        .attr("alt", alternativeTexts.expandedResults);
    $("div.treatment-density button").addClass("expanded");
}

function compactDensity() {
    $("li.result").addClass("compact");
    $("li.result").removeClass("full");

    $("div.treatment-density button img").attr("src", "/images/icons/collapsed-results.svg")
        .attr("alt", alternativeTexts.compactedResults);
    $("div.treatment-density button").removeClass("expanded");
}

function smoothScrollTo(hash) {
    if (!hash)
        return;

    let newScrollTop = $("a[name='" + hash.substring(1) + "']").offset().top;
    if ($('.framed').length === 0) {
        newScrollTop -= ($('#canlii-header').height() * 2);
    } else {
        newScrollTop += $('#searchFieldsWrapper', parent.document || document).height();
        newScrollTop += $('#framedTopBar', parent.document || document).height();
    }

    $("#tableOfContentsArticleHover, #tableOfContentsLinkHover").css({"display": "none"});
    $(parent.document.querySelector(".search-pane") || 'html, body', document).animate({scrollTop: newScrollTop}, 'smooth'
        , () => {
            setTimeout(() => {
                tocLinkClicked = false;
            }, 100);
        });
}

function initSummaryClickEvent() {
    $("a.summary-parag-link").click(function(e) {
        e.preventDefault();
        $('ul.nav-tabs a[href="#document"]').tab('show');

        let url = $(this).attr("href");
        let hash = url.substring(url.indexOf("#"), url.length);
        smoothScrollTo(hash);
    });
}

function showAltSummaryTab() {
    const altSummaryTrigger = document.querySelector('#altsummary-tab');
    const altSummaryTab = new bootstrap.Tab(altSummaryTrigger);
    altSummaryTab.show();
}

function manageSummaryHash() {
    history.replaceState(null, null, "#summary");
    document.querySelectorAll('#summary-tab-nav button[data-bs-toggle="tab"]').forEach(function (tabButton) {
        tabButton.addEventListener("shown.bs.tab", function (event) {
            const targetId = event.target.getAttribute("data-bs-target");
            history.replaceState(null, null, targetId);
        });
    });
}