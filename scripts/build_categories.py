"""Build src/categories.json from Amazon All-menu department trees."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'src' / 'categories.json'


def child(name: str, node: str | None = None) -> dict:
    if node:
        return {'name': name, 'url': f'/s?rh=n:{node}', 'browseNodeId': str(node)}
    return {'name': name, 'url': f'/s?k={quote_plus(name)}'}


def names(*items: str) -> list[tuple[str, None]]:
    return [(item, None) for item in items]


def dept(name: str, children: list[tuple[str, str | None]], node: str | None = None) -> dict:
    item: dict = {
        'name': name,
        'children': [child(child_name, child_node) for child_name, child_node in children],
    }
    if node:
        item['url'] = f'/s?rh=n:{node}'
        item['browseNodeId'] = str(node)
    return item


def market(departments: list[dict]) -> dict:
    return {'departments': departments}


# Amazon.in All → Shop by Category (names match the hamburger).
IN = market([
    dept('Mobiles, Computers', [
        ('All Mobile Phones', '1389401031'),
        ('Cases & Covers', '1389365031'),
        ('Screen Protectors', '1389366031'),
        ('Power Banks', '1389431031'),
        ('Refurbished Mobiles', '1805560031'),
        ('Tablets', '1375458031'),
        ('Wearable Devices', '2563504031'),
        ('Smart Home', '13773797031'),
        ('Laptops', '1375424031'),
        ('Drives & Storage', '1375392031'),
        ('Printers & Ink', '1375428031'),
        ('Networking Devices', '1375427031'),
        ('Computer Accessories', '1375248031'),
        ('Monitors', '1375412031'),
        ('Desktops', '1375425031'),
        ('Components', '1375391031'),
    ], '976419031'),
    dept('TV, Appliances, Electronics', [
        ('Televisions', '1389375031'),
        ('Home Entertainment Systems', '1389376031'),
        ('Headphones', '1389335031'),
        ('Speakers', '1389336031'),
        ('Home Audio & Theater', '1389337031'),
        ('Cameras', '1388977031'),
        ('Camera Accessories', '1388978031'),
        ('Security Cameras', '1388980031'),
        ('Air Conditioners', '3474656031'),
        ('Refrigerators', '1380365031'),
        ('Washing Machines', '1380369031'),
        ('Kitchen & Home Appliances', '1380367031'),
        ('All Appliances', '976442031'),
    ], '976419031'),
    dept("Men's Fashion", [
        ('T-shirts & Polos', '1968024031'),
        ('Shirts', '1968093031'),
        ('Jeans', '1968120031'),
        ('Innerwear', '1968445031'),
        ('Watches', '2563504031'),
        ('Bags & Luggage', '2454170031'),
        ('Sunglasses', '1968027031'),
        ('Sportswear', '1968446031'),
        ('Shoes', '1983518031'),
    ], '1968024031'),
    dept("Women's Fashion", [
        ('Western Wear', '1968253031'),
        ('Ethnic Wear', '1968256031'),
        ('Lingerie & Nightwear', '1968447031'),
        ('Watches', '1350388031'),
        ('Handbags', '1983378031'),
        ('Gold & Diamond Jewellery', '1951049031'),
        ('Fashion Jewellery', '1951111031'),
        ('Sunglasses', '1968258031'),
        ('Sandals', '1983519031'),
    ], '1968253031'),
    dept('Home, Kitchen, Pets', [
        ('Kitchen & Dining', '1380441031'),
        ('Kitchen Storage', '1380092031'),
        ('Furniture', '1380441031'),
        ('Home Furnishing', '1380012031'),
        ('Home Improvement', '2454175031'),
        ('Garden & Outdoor', '2454175031'),
        ('Pet Supplies', '4792397031'),
        ('Home Decor', '1380013031'),
        ('Indoor Lighting', '1380082031'),
    ], '2454176031'),
    dept('Beauty, Health, Grocery', [
        ('Beauty', '1355016031'),
        ('Luxury Beauty', '5311358031'),
        ('Make-up', '1374407031'),
        ('Health & Personal Care', '1350380031'),
        ('Grocery & Gourmet Foods', '2454178031'),
        ('Household Supplies', '1374357031'),
        ('Nutrition & Wellness', '1374410031'),
        ('Health Care Devices', '1374412031'),
    ], '1355016031'),
    dept('Sports, Fitness, Bags, Luggage', [
        ('Cricket', '3404819031'),
        ('Badminton', '3404820031'),
        ('Cycling', '3404821031'),
        ('Exercise & Fitness', '3404818031'),
        ('Sports Shoes', '1983578031'),
        ('Backpacks', '1983396031'),
        ('Suitcases', '2454170031'),
        ('Travel Accessories', '1983398031'),
    ], '1984443031'),
    dept("Toys, Baby Products, Kids' Fashion", [
        ('Toys & Games', '1350380031'),
        ('Baby Products', '1571274031'),
        ('Diapers', '1950478031'),
        ('Baby Fashion', '1968094031'),
        ("Kids' Fashion", '1968095031'),
        ('STEM Toys', '1350381031'),
        ('Soft Toys', '1350382031'),
    ], '1571274031'),
    dept('Car, Motorbike, Industrial', [
        ('Car Accessories', '4770381031'),
        ('Car Electronics', '4770382031'),
        ('Car Parts', '4770383031'),
        ('Motorbike Accessories & Parts', '4772060031'),
        ('Industrial & Scientific', '5866078031'),
        ('Lab & Scientific', '5866079031'),
    ], '4772060031'),
    dept('Books', [
        ('All Books', '976389031'),
        ('Fiction', '1318157031'),
        ('Textbooks', '4145803031'),
        ('Kindle eBooks', '1634753031'),
        ("Children's Books", '992350031'),
        ('Exam Central', '4145804031'),
    ], '976389031'),
    dept('Movies, Music & Video Games', [
        ('Movies', '976416031'),
        ('Music', '976445031'),
        ('Video Games', '976460031'),
        ('Gaming Consoles', '1375398031'),
        ('Gaming Accessories', '1375399031'),
    ], '976416031'),
])

US = market([
    dept('Electronics', [
        ('TV & Video', '1266092011'),
        ('Home Audio & Theater', '667846011'),
        ('Camera & Photo', '502394'),
        ('Cell Phones & Accessories', '2335752011'),
        ('Headphones', '172541'),
        ('Wearable Technology', '10048700011'),
        ('Portable Audio & Video', '172623'),
        ('Car Electronics', '1077068'),
        ('Musical Instruments', '11091801'),
        ('Electronics Accessories', '281407'),
    ], '172282'),
    dept('Computers', [
        ('Laptops', '565108'),
        ('Desktops', '565098'),
        ('Tablets', '1232597011'),
        ('Monitors', '1292110011'),
        ('Computer Components', '193870011'),
        ('Data Storage', '1292110011'),
        ('Networking Products', '172504'),
        ('Computer Accessories', '172456'),
        ('Printers', '172635'),
    ], '541966'),
    dept('Smart Home', [
        ('Amazon Smart Home', '6563140011'),
        ('Smart Lighting', '6563140011'),
        ('Security Cameras', '524136'),
        ('Plugs & Outlets', '6563140011'),
        ('Thermostats', '6563140011'),
    ], '6563140011'),
    dept('Arts & Crafts', [
        ('Painting & Drawing', '12896121'),
        ('Beading & Jewelry Making', '12896081'),
        ('Crafting', '12896141'),
        ('Fabric', '12899121'),
        ('Sewing', '12899091'),
    ], '2617941011'),
    dept('Automotive', [
        ('Car Care', '15718271'),
        ('Car Electronics', '1077068'),
        ('Exterior Accessories', '15718791'),
        ('Interior Accessories', '15719731'),
        ('Lights & Lighting Accessories', '15730231'),
        ('Motorcycle & Powersports', '346786011'),
        ('Replacement Parts', '15719741'),
        ('Tools & Equipment', '15718761'),
        ('Wheels & Tires', '15706571'),
    ], '15684181'),
    dept('Baby', [
        ('Activity & Entertainment', '166842011'),
        ('Apparel & Accessories', '177225011'),
        ('Baby & Toddler Toys', '196601011'),
        ('Baby Care', '19452189011'),
        ('Diapering', '166764011'),
        ('Feeding', '166771011'),
        ('Gear', '166804011'),
        ('Nursery', '166863011'),
        ('Potty Training', '166805011'),
        ('Pregnancy & Maternity', '166833011'),
        ('Safety', '166806011'),
        ('Strollers & Accessories', '166887011'),
    ], '165796011'),
    dept('Beauty and personal care', [
        ('Makeup', '11058281'),
        ('Skin Care', '11060451'),
        ('Hair Care', '11057241'),
        ('Fragrance', '11056591'),
        ('Foot, Hand & Nail Care', '3777891'),
        ('Tools & Accessories', '11059291'),
        ('Shave & Hair Removal', '3777371'),
        ('Personal Care', '11057651'),
        ('Oral Care', '3777401'),
    ], '3760911'),
    dept("Women's Fashion", [
        ('Clothing', '1040660'),
        ('Shoes', '679337011'),
        ('Jewelry', '719239011'),
        ('Watches', '6358543011'),
        ('Handbags', '15743631'),
        ('Accessories', '2474936011'),
    ], '7147440011'),
    dept("Men's Fashion", [
        ('Clothing', '1040658'),
        ('Shoes', '679255011'),
        ('Watches', '6358544011'),
        ('Accessories', '2474937011'),
    ], '7147441011'),
    dept("Girls' Fashion", [
        ('Clothing', '1040664'),
        ('Shoes', '679312011'),
        ('Jewelry', '3887881'),
        ('Watches', '6358545011'),
        ('Accessories', '2474938011'),
    ], '7147442011'),
    dept("Boys' Fashion", [
        ('Clothing', '1040666'),
        ('Shoes', '679320011'),
        ('Watches', '6358546011'),
        ('Accessories', '2474939011'),
    ], '7147443011'),
    dept('Health and Household', [
        ('Health Care', '3760941'),
        ('Household Supplies', '15342811'),
        ('Vitamins & Dietary Supplements', '3764441'),
        ('Sports Nutrition', '6973663011'),
        ('Baby & Child Care', '10787321'),
        ('Medical Supplies & Equipment', '3775161'),
        ('Wellness & Relaxation', '10079996011'),
    ], '3760901'),
    dept('Home and Kitchen', [
        ('Kitchen & Dining', '284507'),
        ('Bedding', '1063252'),
        ('Bath', '1063236'),
        ('Furniture', '1063306'),
        ('Home Decor', '1063278'),
        ('Wall Art', '3736081'),
        ('Lighting & Ceiling Fans', '495224'),
        ('Event & Party Supplies', '3238155011'),
        ('Heating, Cooling & Air Quality', '3206324011'),
        ('Vacuums & Floor Care', '510106'),
        ('Storage & Organization', '3610841'),
    ], '1055398'),
    dept('Industrial and Scientific', [
        ('Abrasive & Finishing Products', '256167011'),
        ('Additive Manufacturing Products', '6066126011'),
        ('Commercial Door Products', '16310161'),
        ('Cutting Tools', '12897031'),
        ('Fasteners', '16410981'),
        ('Filtration', '393303011'),
        ('Food Service Equipment & Supplies', '16310151'),
        ('Hydraulics, Pneumatics & Plumbing', '2236478011'),
        ('Industrial Electrical', '3066126011'),
        ('Lab & Scientific Products', '317970011'),
        ('Material Handling Products', '134575011'),
        ('Occupational Health & Safety Products', '3180231'),
        ('Power & Hand Tools', '328182011'),
    ], '16310091'),
    dept('Luggage', [
        ('Carry-Ons', '15743241'),
        ('Backpacks', '15743251'),
        ('Garment Bags', '15743261'),
        ('Travel Accessories', '15743281'),
        ('Laptop Bags', '15743271'),
        ('Suitcases', '15743231'),
        ('Kids Luggage', '15743291'),
        ('Messenger Bags', '15743301'),
        ('Umbrellas', '15743311'),
        ('Duffles', '15743321'),
    ], '15743231'),
    dept('Movies & Television', [
        ('Movies', '2625373011'),
        ('TV Shows', '2625374011'),
        ('Blu-ray', '2625375011'),
    ], '2625373011'),
    dept('Pet supplies', [
        ('Dogs', '2975312011'),
        ('Cats', '2975241011'),
        ('Fish & Aquatic Pets', '2975446011'),
        ('Birds', '2975221011'),
        ('Horses', '2972261011'),
        ('Reptiles & Amphibians', '2975452011'),
        ('Small Animals', '2975461011'),
    ], '2619533011'),
    dept('Software', [
        ('Accounting & Finance', '229534'),
        ('Antivirus & Security', '229535'),
        ('Business & Office', '229536'),
        ("Children's", '229537'),
        ('Design & Illustration', '229538'),
        ('Digital Software', '1232597011'),
        ('Education & Reference', '229539'),
        ('Games', '229540'),
        ('Lifestyle & Hobbies', '229541'),
        ('Music', '229542'),
        ('Photography & Graphic Design', '229543'),
        ('Programming & Web Development', '229544'),
        ('Tax Preparation', '229545'),
        ('Utilities', '229546'),
        ('Video', '229547'),
    ], '229534'),
    dept('Sports and Outdoors', [
        ('Sports & Fitness', '3375251'),
        ('Outdoor Recreation', '706813011'),
        ('Sports Fan Shop', '3386071'),
        ('Leisure Sports & Game Room', '706814011'),
    ], '3375251'),
    dept('Tools & Home Improvement', [
        ('Tools & Home Improvement', '228013'),
        ('Power & Hand Tools', '328182011'),
        ('Lamps & Light Fixtures', '495224'),
        ('Kitchen & Bath Fixtures', '3754161'),
        ('Electrical', '495266'),
        ('Hardware', '511228'),
        ('Smart Home', '6563140011'),
    ], '228013'),
    dept('Toys and Games', [
        ('Action Figures & Statues', '165993011'),
        ('Arts & Crafts', '166057011'),
        ('Baby & Toddler Toys', '196601011'),
        ('Building Toys', '166092011'),
        ('Dolls & Accessories', '166118011'),
        ('Dress Up & Pretend Play', '166327011'),
        ('Kids Electronics', '166164011'),
        ('Games', '166220011'),
        ('Grown-Up Toys', '166269011'),
        ('Hobbies', '166027011'),
        ("Kids' Furniture, Décor & Storage", '166333011'),
        ('Learning & Education', '166269011'),
        ('Novelty & Gag Toys', '166282011'),
        ('Party Supplies', '166210011'),
        ('Puppets', '166183011'),
        ('Puzzles', '166359011'),
        ('Sports & Outdoor Play', '166420011'),
        ('Stuffed Animals & Plush Toys', '166514011'),
        ('Toy Remote Control & Play Vehicles', '166508011'),
        ('Tricycles, Scooters & Wagons', '166327011'),
    ], '165793011'),
    dept('Video Games', [
        ('PlayStation 5', '6427814011'),
        ('PlayStation 4', '6427813011'),
        ('Xbox Series X & S', '23508887011'),
        ('Xbox One', '6469269011'),
        ('Nintendo Switch', '16227128011'),
        ('PC', '229575'),
        ('Mac', '229647'),
        ('Nintendo 3DS', '2622269011'),
        ('PlayStation Vita', '3015332011'),
        ('Legacy Systems', '294940'),
        ('Online Game Services', '979082011'),
        ('Virtual Reality', '176225011'),
        ('Nintendo Switch Accessories', '16227129011'),
        ('PlayStation 4 Accessories', '6427831011'),
        ('Xbox One Accessories', '6469286011'),
        ('PlayStation 5 Accessories', '23508888011'),
        ('Xbox Series X & S Accessories', '23508889011'),
    ], '468642'),
])

GB = market([
    dept('Electronics & Photo', [
        ('Televisions', '560864'),
        ('Home Audio & Hi-Fi', '4085611'),
        ('Cameras', '560834'),
        ('Headphones', '4085731'),
        ('Wearable Technology', '117332031'),
        ('Mobile Phones & Accessories', '536066'),
        ('GPS & Navigation', '560854'),
    ], '560798'),
    dept('Computers & Accessories', [
        ('Laptops', '429886031'),
        ('Desktops', '428652031'),
        ('Tablets', '428655031'),
        ('Monitors', '428653031'),
        ('Computer Components', '428654031'),
        ('Storage', '428656031'),
        ('Networking', '428657031'),
        ('Printers', '428658031'),
    ], '340832031'),
    dept('Fashion', [
        ("Women's", '83450031'),
        ("Men's", '83451031'),
        ("Girls'", '83452031'),
        ("Boys'", '83453031'),
        ('Watches', '328229011'),
        ('Luggage', '2454167031'),
        ('Shoes', '362350011'),
    ], '83451031'),
    dept('Home & Kitchen', [
        ('Kitchen & Dining', '11052591'),
        ('Bedding', '11052601'),
        ('Bath', '11052611'),
        ('Furniture', '11052621'),
        ('Home Decor', '11052631'),
        ('Lighting', '213078031'),
        ('Storage', '11052641'),
    ], '11052591'),
    dept('Beauty', [
        ('Makeup', '118427031'),
        ('Skin Care', '118428031'),
        ('Hair Care', '118429031'),
        ('Fragrance', '118430031'),
        ('Tools & Accessories', '118431031'),
    ], '117332031'),
    dept('Health & Personal Care', [
        ('Vitamins & Supplements', '282638011'),
        ('Medical Supplies', '282639011'),
        ('Personal Care', '282640011'),
        ('Household Supplies', '282641011'),
    ], '65801031'),
    dept('Grocery', [
        ('Fresh & Chilled', '344155031'),
        ('Food Cupboard', '344156031'),
        ('Drinks', '344157031'),
        ('Beer, Wine & Spirits', '344158031'),
    ], '344155031'),
    dept('Baby', [
        ('Baby Care', '60032031'),
        ('Nappies', '60033031'),
        ('Feeding', '60034031'),
        ('Pushchairs', '60035031'),
        ('Baby Toys', '60036031'),
    ], '60032031'),
    dept('Toys & Games', [
        ('Action Figures', '468292'),
        ('Arts & Crafts', '468294'),
        ('Building Toys', '468296'),
        ('Dolls', '468298'),
        ('Games', '468300'),
        ('Puzzles', '468302'),
        ('Outdoor Play', '468304'),
    ], '468294'),
    dept('Sports & Outdoors', [
        ('Exercise & Fitness', '319530011'),
        ('Cycling', '319531011'),
        ('Camping & Hiking', '319532011'),
        ('Football', '319533011'),
        ('Running', '319534011'),
    ], '319530011'),
    dept('Car & Motorbike', [
        ('Car Accessories', '248878031'),
        ('Car Care', '248879031'),
        ('Car Electronics', '248880031'),
        ('Motorbike', '248881031'),
        ('Tools & Equipment', '248882031'),
    ], '248878031'),
    dept('Books', [
        ('All Books', '266239'),
        ('Fiction', '62'),
        ("Children's Books", '69'),
        ('Textbooks', '549646'),
        ('Kindle eBooks', '341677031'),
    ], '266239'),
    dept('PC & Video Games', [
        ('PlayStation 5', '300703'),
        ('Xbox Series X & S', '300704'),
        ('Nintendo Switch', '300705'),
        ('PC Games', '300706'),
        ('Accessories', '300707'),
    ], '300703'),
    dept('Pet Supplies', [
        ('Dogs', '340841031'),
        ('Cats', '340842031'),
        ('Fish', '340843031'),
        ('Small Animals', '340844031'),
        ('Birds', '340845031'),
    ], '340841031'),
])

DE = market([
    dept('Elektronik & Foto', [
        ('Fernseher', '761610'),
        ('Kopfhörer', '761620'),
        ('Kameras', '571860'),
        ('Smartwatches', '571870'),
        ('Handy & Zubehör', '1384526031'),
        ('Audio & Hi-Fi', '571880'),
    ], '562066'),
    dept('Computer & Zubehör', [
        ('Laptops', '427954031'),
        ('Desktops', '427955031'),
        ('Tablets', '427956031'),
        ('Monitore', '427957031'),
        ('Komponenten', '427958031'),
        ('Drucker', '427959031'),
    ], '340843031'),
    dept('Fashion', [
        ('Damen', '1981028031'),
        ('Herren', '1981048031'),
        ('Mädchen', '1981068031'),
        ('Jungen', '1981088031'),
        ('Schuhe', '355621011'),
        ('Uhren', '193711031'),
    ], '1981028031'),
    dept('Küche, Haushalt & Wohnen', [
        ('Küche', '3167641'),
        ('Bettwaren', '3312271'),
        ('Möbel', '3312281'),
        ('Dekoration', '3312291'),
        ('Beleuchtung', '3312301'),
    ], '3167641'),
    dept('Beauty', [
        ('Make-up', '84230031'),
        ('Hautpflege', '84231031'),
        ('Haarpflege', '84232031'),
        ('Düfte', '84233031'),
    ], '84230031'),
    dept('Drogerie & Körperpflege', [
        ('Körperpflege', '64187031'),
        ('Gesundheit', '64188031'),
        ('Haushalt', '64189031'),
        ('Vitamine', '64190031'),
    ], '64187031'),
    dept('Lebensmittel & Getränke', [
        ('Lebensmittel', '340846031'),
        ('Getränke', '340847031'),
        ('Kaffee & Tee', '340848031'),
    ], '340846031'),
    dept('Baby', [
        ('Baby Pflege', '355621011'),
        ('Windeln', '355622011'),
        ('Ernährung', '355623011'),
        ('Kinderwagen', '355624011'),
    ], '355621011'),
    dept('Spielzeug', [
        ('Actionfiguren', '12950651'),
        ('Bau- & Konstruktionsspielzeug', '12950661'),
        ('Puppen', '12950671'),
        ('Spiele', '12950681'),
        ('Puzzles', '12950691'),
    ], '12950651'),
    dept('Sport & Freizeit', [
        ('Fitness', '16435051'),
        ('Camping', '16435061'),
        ('Radsport', '16435071'),
        ('Fußball', '16435081'),
    ], '16435051'),
    dept('Auto & Motorrad', [
        ('Autozubehör', '78191031'),
        ('Autoelektronik', '78192031'),
        ('Motorrad', '78193031'),
        ('Ersatzteile', '78194031'),
    ], '78191031'),
    dept('Bücher', [
        ('Alle Bücher', '186606'),
        ('Belletristik', '186652'),
        ('Kinderbücher', '186654'),
        ('Fachbücher', '186656'),
        ('Kindle eBooks', '530886031'),
    ], '186606'),
    dept('Games', [
        ('PlayStation 5', '300703'),
        ('Xbox Series X & S', '300704'),
        ('Nintendo Switch', '300705'),
        ('PC-Spiele', '300706'),
    ], '300703'),
    dept('Haustier', [
        ('Hund', '340849031'),
        ('Katze', '340850031'),
        ('Fisch', '340851031'),
        ('Kleintiere', '340852031'),
    ], '340849031'),
])

FR = market([
    dept('High-Tech', names('Télévisions', 'Écouteurs', 'Appareils photo', 'Téléphones', 'Objets connectés')),
    dept('Informatique', names('Ordinateurs portables', 'Ordinateurs de bureau', 'Tablettes', 'Écrans', 'Composants')),
    dept('Mode', names('Femme', 'Homme', 'Fille', 'Garçon', 'Chaussures', 'Montres')),
    dept('Cuisine & Maison', names('Cuisine', 'Linge de maison', 'Meubles', 'Décoration', 'Éclairage')),
    dept('Beauté', names('Maquillage', 'Soin de la peau', 'Cheveux', 'Parfums')),
    dept('Santé & Soins du corps', names('Soins du corps', 'Santé', 'Entretien de la maison')),
    dept('Épicerie', names('Alimentation', 'Boissons', 'Café & Thé')),
    dept('Bébé & Puériculture', names('Soins bébé', 'Couches', 'Alimentation', 'Poussettes')),
    dept('Jeux et Jouets', names('Figurines', 'Jeux de construction', 'Poupées', 'Jeux de société')),
    dept('Sports et Loisirs', names('Fitness', 'Camping', 'Cyclisme', 'Football')),
    dept('Auto et Moto', names('Accessoires auto', 'Électronique auto', 'Moto')),
    dept('Livres', names('Tous les livres', 'Littérature', 'Livres jeunesse', 'Scolaire', 'Kindle')),
    dept('Jeux vidéo', names('PlayStation 5', 'Xbox Series X & S', 'Nintendo Switch', 'PC')),
    dept('Animalerie', names('Chien', 'Chat', 'Poisson', 'Petits animaux')),
])

IT = market([
    dept('Elettronica', names('TV', 'Cuffie', 'Fotocamere', 'Smartphone', 'Wearable')),
    dept('Informatica', names('Notebook', 'Desktop', 'Tablet', 'Monitor', 'Componenti')),
    dept('Moda', names('Donna', 'Uomo', 'Bambina', 'Bambino', 'Scarpe', 'Orologi')),
    dept('Casa e cucina', names('Cucina', 'Biancheria', 'Mobili', 'Decorazioni', 'Illuminazione')),
    dept('Bellezza', names('Trucco', 'Cura della pelle', 'Capelli', 'Profumi')),
    dept('Salute e cura della persona', names('Cura della persona', 'Salute', 'Casa')),
    dept('Alimentari e cura della casa', names('Alimentari', 'Bevande', 'Caffè e tè')),
    dept('Prima infanzia', names('Cura del bambino', 'Pannolini', 'Alimentazione', 'Passeggini')),
    dept('Giochi e giocattoli', names('Action figure', 'Costruzioni', 'Bambole', 'Giochi da tavolo')),
    dept('Sport e tempo libero', names('Fitness', 'Camping', 'Ciclismo', 'Calcio')),
    dept('Auto e Moto', names('Accessori auto', 'Elettronica auto', 'Moto')),
    dept('Libri', names('Tutti i libri', 'Narrativa', 'Bambini', 'Scolastici', 'Kindle')),
    dept('Videogiochi', names('PlayStation 5', 'Xbox Series X & S', 'Nintendo Switch', 'PC')),
    dept('Prodotti per animali', names('Cane', 'Gatto', 'Pesci', 'Piccoli animali')),
])

ES = market([
    dept('Electrónica', names('Televisores', 'Auriculares', 'Cámaras', 'Móviles', 'Wearables')),
    dept('Informática', names('Portátiles', 'Sobremesa', 'Tablets', 'Monitores', 'Componentes')),
    dept('Moda', names('Mujer', 'Hombre', 'Niña', 'Niño', 'Zapatos', 'Relojes')),
    dept('Hogar y cocina', names('Cocina', 'Ropa de cama', 'Muebles', 'Decoración', 'Iluminación')),
    dept('Belleza', names('Maquillaje', 'Cuidado de la piel', 'Cabello', 'Perfumes')),
    dept('Salud y cuidado personal', names('Cuidado personal', 'Salud', 'Hogar')),
    dept('Alimentación y bebidas', names('Alimentación', 'Bebidas', 'Café y té')),
    dept('Bebé', names('Cuidado del bebé', 'Pañales', 'Alimentación', 'Cochecitos')),
    dept('Juguetes y juegos', names('Figuras', 'Construcción', 'Muñecas', 'Juegos de mesa')),
    dept('Deportes y aire libre', names('Fitness', 'Camping', 'Ciclismo', 'Fútbol')),
    dept('Coche y moto', names('Accesorios coche', 'Electrónica coche', 'Moto')),
    dept('Libros', names('Todos los libros', 'Ficción', 'Infantil', 'Texto', 'Kindle')),
    dept('Videojuegos', names('PlayStation 5', 'Xbox Series X & S', 'Nintendo Switch', 'PC')),
    dept('Productos para mascotas', names('Perros', 'Gatos', 'Peces', 'Pequeños animales')),
])


def clone_english_tree(source: dict, renames: dict[str, str] | None = None) -> dict:
    """Copy a tree, optionally renaming departments."""
    departments = []
    for item in source['departments']:
        name = (renames or {}).get(item['name'], item['name'])
        copied = dict(item)
        copied['name'] = name
        copied['children'] = [dict(child_item) for child_item in item['children']]
        departments.append(copied)
    return market(departments)


CA = clone_english_tree(US)
AU = clone_english_tree(US, {
    'Health and Household': 'Health, Household & Personal Care',
    'Movies & Television': 'Movies & TV',
})
IE = clone_english_tree(GB)
SG = clone_english_tree(US, {
    "Women's Fashion": 'Fashion',
})

JP = market([
    dept('家電＆カメラ', names('テレビ', 'ヘッドホン', 'カメラ', 'スマートフォン', 'ウェアラブル')),
    dept('パソコン・周辺機器', names('ノートパソコン', 'デスクトップ', 'タブレット', 'モニター', 'PCパーツ')),
    dept('ファッション', names('レディース', 'メンズ', 'キッズ', '靴', '腕時計')),
    dept('ホーム＆キッチン', names('キッチン', '寝具', '家具', 'インテリア', '照明')),
    dept('ビューティー', names('メイク', 'スキンケア', 'ヘアケア', '香水')),
    dept('食品・飲料', names('食品', '飲料', 'コーヒー・お茶')),
    dept('ベビー＆マタニティ', names('ベビーケア', 'おむつ', '授乳・離乳', 'ベビーカー')),
    dept('おもちゃ', names('フィギュア', 'ブロック', '人形', 'ゲーム')),
    dept('スポーツ＆アウトドア', names('フィットネス', 'キャンプ', '自転車', 'サッカー')),
    dept('車＆バイク', names('カー用品', 'カーエレクトロニクス', 'バイク')),
    dept('本', names('すべての本', '小説', '児童書', 'Kindle本')),
    dept('ゲーム', names('PlayStation 5', 'Xbox', 'Nintendo Switch', 'PCゲーム')),
    dept('ペット用品', names('犬', '猫', '魚', '小動物')),
])

MX = market([
    dept('Electrónicos', names('Televisores', 'Audífonos', 'Cámaras', 'Celulares', 'Wearables')),
    dept('Computadoras', names('Laptops', 'Desktops', 'Tablets', 'Monitores', 'Componentes')),
    dept('Ropa, Zapatos y Accesorios', names('Mujer', 'Hombre', 'Niña', 'Niño', 'Zapatos', 'Relojes')),
    dept('Hogar y Cocina', names('Cocina', 'Ropa de cama', 'Muebles', 'Decoración', 'Iluminación')),
    dept('Belleza', names('Maquillaje', 'Cuidado de la piel', 'Cabello', 'Fragancias')),
    dept('Salud y Cuidado Personal', names('Cuidado personal', 'Salud', 'Hogar')),
    dept('Alimentos y Bebidas', names('Alimentos', 'Bebidas', 'Café y té')),
    dept('Bebé', names('Cuidado del bebé', 'Pañales', 'Alimentación', 'Carriolas')),
    dept('Juegos y juguetes', names('Figuras', 'Construcción', 'Muñecas', 'Juegos de mesa')),
    dept('Deportes y Aire Libre', names('Fitness', 'Camping', 'Ciclismo', 'Fútbol')),
    dept('Automotriz', names('Accesorios', 'Electrónica', 'Refacciones')),
    dept('Libros', names('Todos los libros', 'Ficción', 'Infantil', 'Kindle')),
    dept('Videojuegos', names('PlayStation 5', 'Xbox Series X & S', 'Nintendo Switch', 'PC')),
    dept('Mascotas', names('Perros', 'Gatos', 'Peces', 'Pequeñas mascotas')),
])

BR = market([
    dept('Eletrônicos', names('TVs', 'Fones de ouvido', 'Câmeras', 'Celulares', 'Wearables')),
    dept('Informática', names('Notebooks', 'Desktops', 'Tablets', 'Monitores', 'Componentes')),
    dept('Moda', names('Feminino', 'Masculino', 'Meninas', 'Meninos', 'Calçados', 'Relógios')),
    dept('Casa', names('Cozinha', 'Cama, Mesa e Banho', 'Móveis', 'Decoração', 'Iluminação')),
    dept('Beleza', names('Maquiagem', 'Cuidados com a pele', 'Cabelo', 'Perfumes')),
    dept('Saúde e Cuidados Pessoais', names('Cuidados pessoais', 'Saúde', 'Casa')),
    dept('Alimentos e Bebidas', names('Alimentos', 'Bebidas', 'Café e chá')),
    dept('Bebês', names('Cuidados com o bebê', 'Fraldas', 'Alimentação', 'Carrinhos')),
    dept('Brinquedos e Jogos', names('Bonecos', 'Montar', 'Bonecas', 'Jogos de tabuleiro')),
    dept('Esportes e Aventura', names('Fitness', 'Camping', 'Ciclismo', 'Futebol')),
    dept('Automotivo', names('Acessórios', 'Eletrônicos', 'Peças')),
    dept('Livros', names('Todos os livros', 'Ficção', 'Infantil', 'Kindle')),
    dept('Games', names('PlayStation 5', 'Xbox Series X & S', 'Nintendo Switch', 'PC')),
    dept('Pet Shop', names('Cães', 'Gatos', 'Peixes', 'Pequenos animais')),
])

NL = market([
    dept('Elektronica', names('Televisies', 'Koptelefoons', 'Camera’s', 'Mobiele telefoons', 'Wearables')),
    dept('Computers', names('Laptops', 'Desktops', 'Tablets', 'Monitoren', 'Onderdelen')),
    dept('Mode', names('Dames', 'Heren', 'Meisjes', 'Jongens', 'Schoenen', 'Horloges')),
    dept('Wonen & keuken', names('Keuken', 'Beddengoed', 'Meubels', 'Decoratie', 'Verlichting')),
    dept('Beauty', names('Make-up', 'Huidverzorging', 'Haarverzorging', 'Parfum')),
    dept('Gezondheid', names('Persoonlijke verzorging', 'Gezondheid', 'Huishouden')),
    dept('Boeken', names('Alle boeken', 'Fictie', 'Kinderboeken', 'Kindle')),
    dept('Speelgoed', names('Actiefiguren', 'Bouwsets', 'Poppen', 'Bordspellen')),
    dept('Sport & outdoor', names('Fitness', 'Kamperen', 'Fietsen', 'Voetbal')),
    dept('Auto & motor', names('Auto-accessoires', 'Auto-elektronica', 'Motor')),
    dept('Games', names('PlayStation 5', 'Xbox Series X & S', 'Nintendo Switch', 'PC')),
    dept('Huisdieren', names('Honden', 'Katten', 'Vissen', 'Kleine dieren')),
])

BE = clone_english_tree(NL, {
    'Elektronica': 'High-tech',
    'Wonen & keuken': 'Cuisine et maison',
    'Gezondheid': 'Santé',
    'Boeken': 'Livres',
    'Speelgoed': 'Jeux et Jouets',
    'Sport & outdoor': 'Sports et Loisirs',
    'Auto & motor': 'Auto et Moto',
    'Huisdieren': 'Animalerie',
})

SE = market([
    dept('Elektronik', names('TV', 'Hörlurar', 'Kameror', 'Mobiler', 'Wearables')),
    dept('Datorer', names('Bärbara datorer', 'Stationära datorer', 'Surfplattor', 'Skärmar', 'Komponenter')),
    dept('Mode', names('Dam', 'Herr', 'Flickor', 'Pojkar', 'Skor', 'Klockor')),
    dept('Hem & kök', names('Kök', 'Sängkläder', 'Möbler', 'Inredning', 'Belysning')),
    dept('Skönhet', names('Makeup', 'Hudvård', 'Hårvård', 'Parfym')),
    dept('Hälsa', names('Personvård', 'Hälsa', 'Hushåll')),
    dept('Böcker', names('Alla böcker', 'Skönlitteratur', 'Barnböcker', 'Kindle')),
    dept('Leksaker', names('Actionfigurer', 'Byggleksaker', 'Dockor', 'Sällskapsspel')),
    dept('Sport & outdoor', names('Fitness', 'Camping', 'Cykling', 'Fotboll')),
    dept('Bil & motor', names('Biltillbehör', 'Bilelektronik', 'Motorcykel')),
    dept('Spel', names('PlayStation 5', 'Xbox Series X & S', 'Nintendo Switch', 'PC')),
    dept('Husdjur', names('Hund', 'Katt', 'Fisk', 'Smådjur')),
])

PL = market([
    dept('Elektronika', names('Telewizory', 'Słuchawki', 'Aparaty', 'Telefony', 'Wearable')),
    dept('Komputery', names('Laptopy', 'Komputery stacjonarne', 'Tablety', 'Monitory', 'Podzespoły')),
    dept('Moda', names('Kobieta', 'Mężczyzna', 'Dziewczynka', 'Chłopiec', 'Buty', 'Zegarki')),
    dept('Dom i kuchnia', names('Kuchnia', 'Pościel', 'Meble', 'Dekoracje', 'Oświetlenie')),
    dept('Uroda', names('Makijaż', 'Pielęgnacja skóry', 'Włosy', 'Perfumy')),
    dept('Zdrowie', names('Pielęgnacja', 'Zdrowie', 'Dom')),
    dept('Książki', names('Wszystkie książki', 'Literatura', 'Dla dzieci', 'Kindle')),
    dept('Zabawki', names('Figurki', 'Klocki', 'Lalki', 'Gry planszowe')),
    dept('Sport i turystyka', names('Fitness', 'Camping', 'Rowery', 'Piłka nożna')),
    dept('Motoryzacja', names('Akcesoria samochodowe', 'Elektronika samochodowa', 'Motocykle')),
    dept('Gry', names('PlayStation 5', 'Xbox Series X & S', 'Nintendo Switch', 'PC')),
    dept('Zwierzęta', names('Psy', 'Koty', 'Ryby', 'Małe zwierzęta')),
])

TR = market([
    dept('Elektronik', names('Televizyonlar', 'Kulaklıklar', 'Kameralar', 'Cep Telefonları', 'Giyilebilir Teknoloji')),
    dept('Bilgisayar', names('Dizüstü', 'Masaüstü', 'Tablet', 'Monitör', 'Bileşenler')),
    dept('Moda', names('Kadın', 'Erkek', 'Kız Çocuk', 'Erkek Çocuk', 'Ayakkabı', 'Saat')),
    dept('Ev ve Mutfak', names('Mutfak', 'Yatak', 'Mobilya', 'Dekorasyon', 'Aydınlatma')),
    dept('Güzellik', names('Makyaj', 'Cilt Bakımı', 'Saç Bakımı', 'Parfüm')),
    dept('Kitap', names('Tüm kitaplar', 'Kurgu', 'Çocuk', 'Kindle')),
    dept('Oyuncak', names('Aksiyon figürleri', 'Yapı oyuncakları', 'Bebekler', 'Kutu oyunları')),
    dept('Spor', names('Fitness', 'Kamp', 'Bisiklet', 'Futbol')),
    dept('Otomotiv', names('Aksesuar', 'Elektronik', 'Motosiklet')),
    dept('Oyuncular', names('PlayStation 5', 'Xbox Series X & S', 'Nintendo Switch', 'PC')),
    dept('Evcil Hayvan', names('Köpek', 'Kedi', 'Balık', 'Küçük hayvanlar')),
])

AE = market([
    dept('Electronics', names('Televisions', 'Headphones', 'Cameras', 'Mobiles', 'Wearables')),
    dept('Computers', names('Laptops', 'Desktops', 'Tablets', 'Monitors', 'Components')),
    dept('Fashion', names("Women's", "Men's", "Girls'", "Boys'", 'Shoes', 'Watches')),
    dept('Home & Kitchen', names('Kitchen', 'Bedding', 'Furniture', 'Home Decor', 'Lighting')),
    dept('Beauty', names('Makeup', 'Skin Care', 'Hair Care', 'Fragrance')),
    dept('Grocery', names('Food', 'Drinks', 'Coffee & Tea')),
    dept('Baby', names('Baby Care', 'Diapers', 'Feeding', 'Strollers')),
    dept('Toys', names('Action Figures', 'Building Toys', 'Dolls', 'Board Games')),
    dept('Sports', names('Fitness', 'Camping', 'Cycling', 'Football')),
    dept('Automotive', names('Car Accessories', 'Car Electronics', 'Motorcycle')),
    dept('Books', names('All Books', 'Fiction', "Children's Books", 'Kindle')),
    dept('Video Games', names('PlayStation 5', 'Xbox Series X & S', 'Nintendo Switch', 'PC')),
    dept('Pet Supplies', names('Dogs', 'Cats', 'Fish', 'Small Animals')),
])

SA = clone_english_tree(AE)
EG = clone_english_tree(AE)
ZA = clone_english_tree(AE)

TREES = {
    'US': US,
    'CA': CA,
    'MX': MX,
    'BR': BR,
    'GB': GB,
    'IE': IE,
    'DE': DE,
    'FR': FR,
    'IT': IT,
    'ES': ES,
    'NL': NL,
    'BE': BE,
    'SE': SE,
    'PL': PL,
    'TR': TR,
    'SA': SA,
    'AE': AE,
    'EG': EG,
    'ZA': ZA,
    'IN': IN,
    'JP': JP,
    'AU': AU,
    'SG': SG,
}


def main() -> None:
    OUT.write_text(json.dumps(TREES, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    departments = sum(len(tree['departments']) for tree in TREES.values())
    children = sum(
        len(department['children'])
        for tree in TREES.values()
        for department in tree['departments']
    )
    print(f'Wrote {OUT} ({len(TREES)} markets, {departments} departments, {children} subcategories)')


if __name__ == '__main__':
    main()
