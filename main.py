x = """# The Sims 4 DLC - Checklist

## Expansion Packs

- [x] EP01 - Get To Work
- [x] EP02 - Get Together
- [x] EP03 - City Living
- [ ] EP04 - Cats & Dogs
- [x] EP05 - Seasons
- [x] EP06 - Get Famous
- [x] EP07 - Island Living
- [x] EP08 - Discover University
- [x] EP09 - Eco Lifestyle
- [x] EP10 - Snowy Escape
- [x] EP11 - Cottage Living
- [x] EP12 - High School Years
- [ ] EP13 - Growing Together
- [ ] EP14 - Horse Ranch
- [x] EP15 - For Rent
- [x] EP16 - Lovestruck
- [ ] EP17 - Life & Death
- [ ] EP18 - Businesses & Hobbies
- [ ] EP19 - Enchanted by Nature
- [ ] EP20 - Adventure Awaits

## Game Packs

- [x] GP01 - Outdoor Retreat
- [x] GP02 - Spa Day
- [ ] GP03 - Dine Out
- [ ] GP04 - Vampires
- [ ] GP05 - Parenthood
- [ ] GP06 - Jungle Adventure
- [ ] GP07 - StrangerVille
- [ ] GP08 - Realm of Magic
- [ ] GP09 - Journey to Batuu
- [ ] GP10 - Dream Home Decorator
- [ ] GP11 - My Wedding Stories
- [ ] GP12 - Werewolves

## Stuff Packs

- [x] SP01 - Luxury Party
- [x] SP02 - Perfect Patio
- [ ] SP03 - Cool Kitchen
- [ ] SP04 - Spooky Stuff
- [x] SP05 - Movie Hangout
- [x] SP06 - Romantic Garden
- [ ] SP07 - Kids Room
- [x] SP08 - Backyard
- [ ] SP09 - Vintage Glamour
- [x] SP10 - Bowling Night
- [x] SP11 - Fitness
- [ ] SP12 - Toddler
- [x] SP13 - Laundry Day
- [ ] SP14 - My First Pet
- [x] SP15 - Moschino
- [x] SP16 - Tiny Living
- [ ] SP17 - Nifty Knitting
- [ ] SP18 - Paranormal
- [ ] SP46 - Home Chef Hustle
- [ ] SP49 - Crystal Creations

## Kits

- [ ] SP21 - Country Kitchen
- [ ] SP22 - Bust The Dust
- [ ] SP23 - Courtyard Oasis
- [ ] SP24 - Fashion Street
- [ ] SP25 - Industrial Loft
- [ ] SP26 - Incheon Arrivals
- [ ] SP28 - Modern Menswear
- [ ] SP29 - Blooming Rooms
- [x] SP30 - Carnaval Streetwear
- [ ] SP31 - Decor to the Max
- [ ] SP32 - Moonlight Chic
- [ ] SP33 - Little Campers
- [x] SP34 - First Fits
- [ ] SP35 - Desert Luxe
- [ ] SP36 - Pastel Pop
- [ ] SP37 - Everyday Clutter
- [x] SP38 - Simtimates Collection
- [ ] SP40 - Greenhouse Haven
- [x] SP41 - Basement Treasures
- [ ] SP42 - Grunge Revival
- [ ] SP43 - Book Nook
- [x] SP44 - Poolside Splash
- [ ] SP45 - Modern Luxe
- [ ] SP47 - Castle Estate
- [ ] SP48 - Goth Galore
- [ ] SP50 - Urban Homage
- [x] SP51 - Party Essentials
- [ ] SP52 - Riviera Retreat
- [ ] SP53 - Cozy Bistro
- [ ] SP54 - Artist Studio
- [ ] SP55 - Storybook Nursery
- [x] SP56 - Sweet Slumber Party
- [ ] SP57 - Cozy Kitsch
- [ ] SP58 - Comfy Gamer
- [ ] SP59 - Secret Sanctuary
- [ ] SP60 - Casanova Cave
- [ ] SP61 - Refined Living Room
- [ ] SP62 - Business Chic
- [ ] SP63 - Sleek Bathroom
- [x] SP64 - Sweet Allure
- [ ] SP66 - Golden Years
- [ ] SP67 - Kitchen Clutter
- [ ] SP69 - Autumn Apparel
- [ ] SP71 - Grange Mudroom
- [ ] SP72 - Essential Glam

## Free Stuff

- [x] FP01 - Holiday Celebration"""

# -disablepacks:EP19,GP12,SP18
with open('base.txt', 'w') as f:
    f.write(x.replace('[x]', '[ ]'))

with open('main.txt', 'w') as f:
    f.write(x)
    with open('main_disable.txt', 'w') as f2:
        disabled = []
        for line in x.splitlines():
            if line.startswith('- [ ]'):
                code = line.split(' - ')[0].split('] ')[1]
                disabled.append(code)
        f2.write('-disablepacks:' + ','.join(disabled))