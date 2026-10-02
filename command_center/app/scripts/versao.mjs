// Versão do app (#74): o nome da versão vem do package.json ("1.0.0") e o número do build
// vem do CI (BUILD_NUMBER = número da execução do GitHub Actions). As duas lojas exigem que o
// número do build sempre suba; o run_number do Actions sempre sobe.
import { readFileSync, writeFileSync } from 'node:fs'

const versao = JSON.parse(readFileSync('package.json', 'utf8')).version
const build = String(parseInt(process.env.BUILD_NUMBER || '1', 10))
if (!/^\d+\.\d+\.\d+$/.test(versao)) throw new Error(`versão inválida no package.json: ${versao}`)

const gradle = 'android/app/build.gradle'
writeFileSync(gradle, readFileSync(gradle, 'utf8')
  .replace(/versionCode \d+/, `versionCode ${build}`)
  .replace(/versionName "[^"]*"/, `versionName "${versao}"`))

const pbx = 'ios/App/App.xcodeproj/project.pbxproj'
writeFileSync(pbx, readFileSync(pbx, 'utf8')
  .replace(/CURRENT_PROJECT_VERSION = [^;]+;/g, `CURRENT_PROJECT_VERSION = ${build};`)
  .replace(/MARKETING_VERSION = [^;]+;/g, `MARKETING_VERSION = ${versao};`))

console.log(`app ${versao} (build ${build})`)
