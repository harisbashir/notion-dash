document.addEventListener('input', (event) => {
  const target = event.target.dataset.filter;
  if (!target) return;
  const query = event.target.value.toLocaleLowerCase();
  document.querySelectorAll(`${target} [data-search]`).forEach((row) => {
    row.hidden = !row.dataset.search.toLocaleLowerCase().includes(query);
  });
});
const scheme = window.matchMedia('(prefers-color-scheme: dark)');
function updateTheme() {
  document.querySelector('meta[name="theme-color"]')?.setAttribute(
    'content', scheme.matches ? '#0F1D20' : '#E9EFEC'
  );
}
scheme.addEventListener('change', updateTheme);
updateTheme();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
document.addEventListener('htmx:beforeSwap', (event) => {
  if (event.detail.xhr.status === 503) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});
