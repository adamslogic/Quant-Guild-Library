// Drag-and-drop + file-picker wiring for the upload landing page.
(function () {
  const dropzone = document.getElementById("dropzone");
  const input = document.getElementById("file-input");
  const nameEl = document.getElementById("file-name");
  if (!dropzone || !input) return;

  const showName = () => {
    nameEl.textContent = input.files.length ? "✓ " + input.files[0].name : "";
  };

  // Clicking anywhere in the dropzone opens the native file picker.
  dropzone.addEventListener("click", () => input.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  input.addEventListener("change", showName);

  // Visual feedback + file capture for drag-and-drop.
  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      showName();
    }
  });
})();
