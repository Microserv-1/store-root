# Autoria da dupla

- Este checkout é usado pela Pessoa A (Yuri). Seus commits podem ir ao `store-root`, Account, Auth, Gateway e documentação A.
- Os repositórios/submódulos `api/product`, `api/order` e `api/exchange` pertencem à Pessoa B. Não criar commits, fazer push ou alterar a autoria Git nesses repositórios em nome da Pessoa A.
- Para mudanças necessárias em serviços de B, fazer análise/testes e registrar instruções e patches em Markdown no repositório principal. A própria Pessoa B revisa, implementa e publica seus commits.
- Não usar `--author`, amend ou cherry-pick para apresentar código/commits de A como autoria de B.
- Atualizar os ponteiros dos submódulos na raiz somente para commits que B tenha publicado. Registrar nos relatórios exatamente quais versões foram testadas.
- A regra de autoria só pode ser excepcionada por instrução explícita posterior do usuário.
