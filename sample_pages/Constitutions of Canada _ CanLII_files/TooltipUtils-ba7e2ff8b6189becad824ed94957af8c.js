var TooltipUtils = {

	displayCitationTextarea : function(citationTextContainerId) {
		// jquery does not support retrieving an element by id with special characters (like dots), so we use straight javascript
		var citationElement = document.getElementById(citationTextContainerId);
		$(citationElement).toggle(); 
		if (!isSmartphone()) {
			this.ajustContainerHeight(citationTextContainerId);
		}
		Tipped.refresh(lastTippedElement); 
		$(citationElement).select();
	},

	ajustContainerHeight : function(id, maxHeight) {
	   var text = id && id.style ? id : document.getElementById(id);
	   if (!text)
	      return;

	   /* Accounts for rows being deleted, pixel value may need adjusting */
	   if (text.clientHeight == text.scrollHeight) {
	      text.style.height = "30px";
	   }

	   var adjustedHeight = text.clientHeight;
	   if (!maxHeight || maxHeight > adjustedHeight) {
	      adjustedHeight = Math.max(text.scrollHeight, adjustedHeight);
	      if (maxHeight)
	         adjustedHeight = Math.min(maxHeight, adjustedHeight);
	      if (adjustedHeight > text.clientHeight)
	         text.style.height = adjustedHeight + "px";
	   }
	},

	createHelpPopover : function(elem, templateSelector, containerSelector, popoverCloserSelector) {
		let template = document.querySelector(templateSelector);
		let content = template.innerHTML;
		
		$(elem).popover({
			trigger: 'click',
			placement : 'bottom',
			html: true,
			content: content,
			container: $(containerSelector).first()
		});
		
		$(elem).on('shown.bs.popover', function () {
		    $(popoverCloserSelector).click(function() {
				$(elem).popover('hide');
			});
		});
	}
};

