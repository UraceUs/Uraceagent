"""Site novo da URACE (#148), servido pela VPS em novo.urace.us.

Dono, 07/10: *"faça um novo na nossa vps respeitando o desing que esta no site urace.us mas
com uma parte de nossos conceitos e use nossa area do cliente, calendario e integre tudo"*.

- `conteudo.py`: os textos, preços e fotos do urace.us de hoje (07/10), num lugar só;
- `paginas.py`: o HTML de cada página, montado no servidor (o Google lê sem JavaScript);
- `static/`: CSS, o script da agenda, fotos em WebP (≤ 1600 px, sem EXIF) e as fontes.

A rota fica em `api/vitrine.py` e só responde nos endereços do site (`CC_SITE_HOSTS`).
"""
