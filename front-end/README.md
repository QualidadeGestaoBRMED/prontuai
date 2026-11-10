This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

## Deploy de produção

O front sobe pela Vercel, separado do back-end. A conferência `ops/deploy/conferir_producao_sem_ferramentas_de_staging.sh` vale só para o deploy do back-end.

## Testes em staging

As ferramentas só de staging ficam em `/admin/staging` (só ADMIN), com o código em `components/staging/` e `lib/staging.ts` (e, no back-end, em `app/staging/`). O código pode ir para a `v1`: o que as liga são as variáveis de ambiente, nunca a branch.

- Front: `FERRAMENTAS_DE_STAGING=true` nas variáveis de ambiente da Vercel **só do ambiente de staging**. É variável de servidor, sem `NEXT_PUBLIC_`. Sem ela, `/admin/staging` responde 404 já no `middleware.ts`, antes do login, e o proxy não repassa `/v1/testes-staging`.
- Back-end: `APP_ENV=staging` e `FERRAMENTAS_DE_STAGING=true` (ver `back-end/app/staging/__init__.py`).

O card "Testes em staging: pedidos guardados" liga ou desliga a função sem reiniciar nada.
