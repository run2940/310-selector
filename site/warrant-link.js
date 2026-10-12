async function configureWarrantLink() {
  const link = document.querySelector('#warrant-launch');
  const status = document.querySelector('#warrant-status');
  try {
    const response = await fetch('warrant-link.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('Link configuration unavailable');
    const config = await response.json();
    const url = new URL(String(config.warrant_calculator_url || '').trim());
    if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) {
      throw new Error('Invalid calculator URL');
    }
    link.href = url.href;
    link.classList.remove('is-hidden');
    status.textContent = '';
    status.classList.add('is-hidden');
  } catch {
    link.removeAttribute('href');
    link.classList.add('is-hidden');
    status.classList.remove('is-hidden');
    status.textContent = '權證計算機尚未開放，請稍後再試。';
  }
}

configureWarrantLink();
