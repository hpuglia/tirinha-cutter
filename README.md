# Tirinha Cutter

Interface visual local para recortar uma tirinha 2x2 em quatro imagens.

## Android com Termux

Execute o bootstrap diretamente no Termux:

```sh
curl -fsSL https://raw.githubusercontent.com/hpuglia/tirinha-cutter/main/bootstrap.py | python
```

O app abre em `http://127.0.0.1:8765`. Use **Fechar app e servidor** no topo da
interface para finalizar também o processo Python que está rodando no Termux.

## Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/hpuglia/tirinha-cutter/main/bootstrap.py | py -
```
