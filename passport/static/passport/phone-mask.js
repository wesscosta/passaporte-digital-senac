/* Formatação progressiva; a validação definitiva continua no servidor. */
(function () {
  "use strict";
  const field = document.querySelector('[data-phone-mask="br-mobile"]');
  if (!field) return;

  function format(value) {
    if (!/^\+?[0-9().\s-]*$/.test(value)) return value;
    let digits = value.replace(/\D/g, "");
    let prefix = "";
    if (value.trim().startsWith("+")) {
      if (!digits.startsWith("55")) return value;
      prefix = "+55 ";
      digits = digits.slice(2);
    } else if (digits.length === 13 && digits.startsWith("55")) {
      prefix = "+55 ";
      digits = digits.slice(2);
    }
    // Não descarta números excedentes: o servidor poderá informar o erro.
    if (digits.length > 11) return value;
    if (!digits) return prefix.trimEnd();
    let output = prefix + "(" + digits.slice(0, 2);
    if (digits.length > 2) output += ") " + digits.slice(2, 7);
    if (digits.length > 7) output += "-" + digits.slice(7);
    return output;
  }

  function positionAfterDigits(value, count) {
    if (count === 0) return 0;
    let seen = 0;
    for (let i = 0; i < value.length; i += 1) {
      if (/\d/.test(value[i]) && ++seen === count) return i + 1;
    }
    return value.length;
  }

  function applyMask() {
    const value = field.value;
    const start = field.selectionStart == null ? value.length : field.selectionStart;
    const atEnd = start === value.length && field.selectionEnd === start;
    const digitsBefore = value.slice(0, start).replace(/\D/g, "").length;
    const formatted = format(value);
    if (formatted === value) return;
    field.value = formatted;
    const caret = atEnd ? formatted.length : positionAfterDigits(formatted, digitsBefore);
    field.setSelectionRange(caret, caret);
  }

  field.addEventListener("input", function (event) {
    if (!event.isComposing) applyMask();
  });
  field.addEventListener("compositionend", applyMask);
  field.addEventListener("beforeinput", function (event) {
    if (event.inputType !== "deleteContentBackward" || event.isComposing) return;
    const start = field.selectionStart;
    if (start == null || start !== field.selectionEnd || start === 0 || /\d/.test(field.value[start - 1])) return;
    let previous = start - 1;
    while (previous >= 0 && !/\d/.test(field.value[previous])) previous -= 1;
    if (previous < 0) return;
    event.preventDefault();
    field.value = field.value.slice(0, previous) + field.value.slice(start);
    field.setSelectionRange(previous, previous);
    applyMask();
  });
  if (field.value) applyMask();
})();