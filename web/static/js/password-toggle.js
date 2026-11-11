document.querySelectorAll('[data-password-toggle]').forEach((button) => {
  button.addEventListener('click', () => {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    const icon = button.querySelector('i');

    if (!input || !icon) {
      return;
    }

    const isVisible = input.type === 'password';
    input.type = isVisible ? 'text' : 'password';
    button.setAttribute('aria-label', isVisible ? 'Ocultar contraseña' : 'Mostrar contraseña');
    button.setAttribute('aria-pressed', String(isVisible));
    icon.classList.toggle('fa-eye', !isVisible);
    icon.classList.toggle('fa-eye-slash', isVisible);
  });
});
