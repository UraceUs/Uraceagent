/* Países da área do cliente (#54): pilotos vêm de fora dos EUA. Código ISO de 2 letras,
 * nome em inglês e o código do telefone. Os EUA primeiro; o resto em ordem alfabética. */
export const PAISES: [string, string, string][] = [
  ['US', 'United States', '+1'], ['CA', 'Canada', '+1'], ['MX', 'Mexico', '+52'], ['BR', 'Brazil', '+55'],
  ['AR', 'Argentina', '+54'], ['AU', 'Australia', '+61'], ['AT', 'Austria', '+43'], ['BS', 'Bahamas', '+1'],
  ['BE', 'Belgium', '+32'], ['BO', 'Bolivia', '+591'], ['CL', 'Chile', '+56'], ['CN', 'China', '+86'],
  ['CO', 'Colombia', '+57'], ['CR', 'Costa Rica', '+506'], ['DK', 'Denmark', '+45'], ['DO', 'Dominican Republic', '+1'],
  ['EC', 'Ecuador', '+593'], ['FI', 'Finland', '+358'], ['FR', 'France', '+33'], ['DE', 'Germany', '+49'],
  ['GT', 'Guatemala', '+502'], ['HN', 'Honduras', '+504'], ['IN', 'India', '+91'], ['IE', 'Ireland', '+353'],
  ['IL', 'Israel', '+972'], ['IT', 'Italy', '+39'], ['JM', 'Jamaica', '+1'], ['JP', 'Japan', '+81'],
  ['NL', 'Netherlands', '+31'], ['NZ', 'New Zealand', '+64'], ['NO', 'Norway', '+47'], ['PA', 'Panama', '+507'],
  ['PY', 'Paraguay', '+595'], ['PE', 'Peru', '+51'], ['PL', 'Poland', '+48'], ['PT', 'Portugal', '+351'],
  ['PR', 'Puerto Rico', '+1'], ['SA', 'Saudi Arabia', '+966'], ['ZA', 'South Africa', '+27'], ['KR', 'South Korea', '+82'],
  ['ES', 'Spain', '+34'], ['SE', 'Sweden', '+46'], ['CH', 'Switzerland', '+41'], ['AE', 'United Arab Emirates', '+971'],
  ['GB', 'United Kingdom', '+44'], ['UY', 'Uruguay', '+598'], ['VE', 'Venezuela', '+58'],
]

export const ddiDe = (pais: string) => PAISES.find(p => p[0] === pais)?.[2] || '+1'
export const nomePais = (pais: string) => PAISES.find(p => p[0] === pais)?.[1] || pais
