# Anthor Endpoint Monitor

Monitor simples em terminal para acompanhar a disponibilidade e a latencia de endpoints definidos localmente.

O projeto executa todos os scripts dentro da pasta `endpoints/`, mede o tempo de resposta, marca sucesso ou falha e mostra um dashboard em tempo real no terminal.

## Estrutura

- `monitor_anthor.py`: monitor principal em Python
- `open_monitor.command`: launcher para abrir o monitor a partir da pasta atual do projeto
- `endpoints/`: pasta com os scripts de verificação de endpoints

## Como executar

Pelo terminal, dentro da pasta do projeto:

```bash
chmod +x open_monitor.command
./open_monitor.command
```

Ou execute direto com Python:

```bash
python3 monitor_anthor.py
```

No macOS, tambem e possivel dar duplo clique em `open_monitor.command`.

## Como funciona a pasta `endpoints`

A pasta `endpoints/` deve existir no repositório, mas o conteudo dela nao deve ser versionado.

Cada arquivo dentro dessa pasta deve ser um script executavel em `zsh`, normalmente contendo um `curl`. O monitor:

1. encontra todos os arquivos da pasta
2. executa um por um
3. mede a duracao
4. interpreta falhas por codigo de saida, timeout ou erro no JSON retornado
5. atualiza o dashboard

Exemplo de endpoint:

```sh
curl 'https://exemplo.com/graphql' \
  -H 'content-type: application/json' \
  --data-raw '{"query":"{ health }"}'
```

## Comportamento do monitor

- intervalo entre ciclos: 30 segundos
- timeout por endpoint: 120 segundos
- historico por endpoint: 30 execucoes
- alerta sonoro quando ocorre falha
- destaque visual em vermelho para endpoints com erro

## Observacoes importantes

- O projeto depende de `python3` e `zsh`.
- O som de alerta usa `afplay` quando disponivel, com fallback para beep no terminal.
- Tokens, cabecalhos de autenticacao e dados sensiveis nao devem ser salvos no Git.
- O `.gitignore` foi configurado para manter a pasta `endpoints/` no repositório, ignorando apenas os arquivos reais dentro dela.
