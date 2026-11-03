# Tirinha Cutter

Ferramenta local para separar uma tirinha em grade **2×2** em quatro arquivos PNG. Interface responsiva para Windows, Linux e Android/Termux.

## Interface 0.2.7

A versão **0.2.7** corrige um erro de sintaxe no JavaScript gerado pelo Python que fazia o seletor de imagem abrir sem efetivamente carregar o arquivo. O carregamento e os controles voltam a funcionar.

## Melhorias de interface (0.2.6)

- **Botão de exportação e status sempre visíveis** no rodapé, inclusive em telas pequenas.
- Controles de corte em **pills compactas**, exibidos somente depois de carregar uma imagem.
- Seleção por arquivo, **arrastar e soltar** ou **colar imagem (Ctrl+V)** no navegador, quando suportado.
- Linhas ajustáveis sobre a prévia, sliders e microajustes de 0,25% (ou setas no canvas).
- Visualização limitada a 4 MP para reduzir travamentos; **arquivos recortados na resolução original**.
- Mensagens de carregamento, sucesso e erro, com possibilidade de tentar novamente.
- Se uma nova imagem falhar, a imagem anterior permanece disponível.
- Se o canvas não estiver disponível, usa prévia simples com ajustes percentuais.
- Se o seletor nativo de pastas falhar, o caminho pode ser digitado manualmente.

Os recortes gerados continuam sendo os quatro quadrantes, salvos por padrão como `1.png`, `2.png`, `3.png` e `4.png`. A opção de nomes individuais com nome e data/hora permanece disponível.

## Android com Termux

Execute o bootstrap diretamente no Termux:

```sh
curl -fsSL https://raw.githubusercontent.com/hpuglia/tirinha-cutter/main/bootstrap.py | python
```

O app abre em `http://127.0.0.1:8765`. Use **Encerrar servidor** no topo da interface para finalizar também o processo Python que está rodando no Termux.

## Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/hpuglia/tirinha-cutter/main/bootstrap.py | py -
```

## Dicas e alternativas

- Caso a colagem não funcione, utilize o seletor de arquivo.
- Caso a janela de pasta não abra, informe manualmente a pasta de destino na seção **Salvar recortes**.
- Se a conexão com o servidor local cair, reinicie o aplicativo pelo comando acima. A interface informa os erros da exportação e permite repetir a tentativa.
- Para reiniciar com a versão publicada, feche o processo anterior antes de executar o bootstrap novamente, evitando conflito na porta `8765`.

Dependência: **Pillow** (`requirements.txt`). O aplicativo roda inteiramente no computador/dispositivo, sem upload das imagens para servidores externos.
