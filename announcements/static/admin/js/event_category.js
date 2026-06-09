(function ($) {
  'use strict';

  // Fieldset heading keywords to HIDE for each category
  var HIDE_FIELDSETS = {
    announcement: ['YouTube', 'Location', 'Registration', 'Event Configuration', 'Configuration'],
    notice:       ['YouTube', 'Location', 'Registration', 'Event Configuration', 'Configuration'],
    workshop:     ['YouTube'],
    event:        [],
  };

  // Individual field IDs whose entire row should be hidden per category
  var HIDE_FIELD_ROWS = {
    announcement: ['id_poster', 'id_event_type', 'id_status'],
    notice:       ['id_poster', 'id_event_type', 'id_status'],
    workshop:     [],
    event:        [],
  };

  function applyCategory(category) {
    // 1. Reset — show everything
    $('fieldset.module').show();
    $('fieldset.module .form-row').show();

    var hideFieldsets  = HIDE_FIELDSETS[category]  || [];
    var hideFieldRows  = HIDE_FIELD_ROWS[category]  || [];

    // 2. Hide full fieldsets by matching heading keyword
    $('fieldset.module h2').each(function () {
      var heading = $(this).text().trim();
      var shouldHide = hideFieldsets.some(function (kw) {
        return heading.indexOf(kw) !== -1;
      });
      if (shouldHide) {
        $(this).closest('fieldset').hide();
      }
    });

    // 3. Hide individual field rows inside visible fieldsets
    hideFieldRows.forEach(function (fieldId) {
      var $field = $('#' + fieldId);
      if ($field.length) {
        $field.closest('.form-row').hide();
      }
    });
  }

  $(document).ready(function () {
    var $category = $('#id_category');
    if (!$category.length) return;

    // Apply on initial page load
    applyCategory($category.val());

    // Apply whenever dropdown changes — no save needed
    $category.on('change', function () {
      applyCategory($(this).val());
    });
  });

})(django.jQuery);
