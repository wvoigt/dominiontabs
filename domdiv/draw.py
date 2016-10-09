import os
import re
import sys

from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont


def split(l, n):
    i = 0
    while i < len(l) - n:
        yield l[i:i + n]
        i += n
    yield l[i:]

class CardPlot(object):
    # This object contains information needed to print a divider on a page.
    # It goes beyond information about the general card/divider to include page specific drawing information.
    # It also includes helpful methods used in manipulating the object.

    def __init__(self, card, x=0, y=0, rotation=0, height=0, width=0, stackHeight=0, rightSide=False, page=0, lineType='line', textTypeFront="card", textTypeBack="rules", cropOnTop=False, cropOnBottom=False, cropOnLeft=False, cropOnRight=False, isTabCentred=False):
        self.card = card
        self.x = x # x location of the lower left corner of the card on the page
        self.y = y # y location of the lower left corner of the card on the page
        self.rotation = rotation # of the card. 0, 90, 180, 270
        self.lineType = lineType # Type of outline to use: line, dot, none
        self.width = width # Width of the divider including any divider to divider spacing
        self.height = height # Height of the divider including any divider to divider spacing
        self.stackHeight = stackHeight # The height of a stack of these cards. Used for interleaving.
        self.textTypeFront = textTypeFront #What card text to put on the front of the divider
        self.textTypeBack = textTypeBack #What card text to put on the back of the divider
        self.cropOnTop = cropOnTop #When true, cropmarks needed along TOP *printed* edge of the card
        self.cropOnBottom = cropOnBottom #When true, cropmarks needed along BOTTOM *printed* edge of the card
        self.cropOnLeft = cropOnLeft #When true, cropmarks needed along LEFT *printed* edge of the card
        self.cropOnRight = cropOnRight #When true, cropmarks needed along RIGHT *printed* edge of the card
        self.page = page # holds page number of this printed card
        self.rightSide = rightSide # When true, the card tab is flipped to the "other" side
        self.isTabCentred = isTabCentred #When true, the tab is centered instead of on the right or left.
        self.LEFT, self.RIGHT, self.TOP, self.BOTTOM = range(1, 5) # directional constants

    def setXY(self, x, y, rotation=None):
        # set the card to the given x,y and optional rotation
        self.x = x
        self.y = y
        if rotation != None:
            self.rotation = rotation

    def rotate(self, delta):
        # rotate the card by amount delta
        self.rotation = (self.rotation + delta) % 360

    def flipFront2Back(self):
        # Flip a card from front to back.  i.e., print the front of the divider on the page's back
        # and print the back of the divider on the page's front.  So what does that mean...
        # The tab moves from right(left) to left(right).
        # And then the divider's text is moved to the other side of the page.
        self.rightSide = not self.rightSide
        self.textTypeFront, self.textTypeBack = self.textTypeBack, self.textTypeFront

    def translate(self, canvas, page_width, backside=False):
        # Translate the page x,y of the lower left of item, taking into account the rotation,
        # and set up the canvas so that (0,0) is now at the lower lower left of the item
        # and the item can be drawn as if it is in the "standard" orientation.
        # So when done, the canvas is set and ready to draw the divider
        x = self.x
        y = self.y
        rotation = self.rotation

        if backside:
            x = page_width - x - self.width

        if self.rotation == 180:
            x += self.width
            y += self.height
        elif self.rotation == 90:
            if backside:
                x += self.width
                rotation = 270
            else:
                y += self.width
        elif self.rotation == 270:
            if backside:
                x += self.width - self.height
                y += self.width
                rotation = 90
            else:
                x += self.height

        rotation = 360 - rotation % 360 # ReportLab rotates counter clockwise, not clockwise.
        canvas.translate(x, y)
        canvas.rotate(rotation)

    def translateCropmarkEnable(self, side):
        # Returns True if a cropmark is needed on that side of the card
        # Takes into account the card's rotation, if the tab is flipped, if the card is next to an edge, etc.

        # First the rotation. The page does not change even if the card is rotated.
        # So need to translate page side to the actual drawn card edge
        if self.rotation == 0:
            sideTop    = self.cropOnTop
            sideBottom = self.cropOnBottom
            sideRight  = self.cropOnRight
            sideLeft   = self.cropOnLeft
        elif self.rotation == 90:
            sideTop    = self.cropOnRight
            sideBottom = self.cropOnLeft
            sideRight  = self.cropOnBottom
            sideLeft   = self.cropOnTop
        elif self.rotation == 180:
            sideTop    = self.cropOnBottom
            sideBottom = self.cropOnTop
            sideRight  = self.cropOnLeft
            sideLeft   = self.cropOnRight
        elif self.rotation == 270:
            sideTop    = self.cropOnLeft
            sideBottom = self.cropOnRight
            sideRight  = self.cropOnTop
            sideLeft   = self.cropOnBottom

        # Now take care of the case where the tab has been flipped
        if self.rightSide:
            sideLeft, sideRight = sideRight, sideLeft

        # Now can return the proper value based upon what side is requested
        if side == self.TOP:
            return sideTop
        elif side == self.BOTTOM:
            return sideBottom
        elif side == self.RIGHT:
            return sideRight
        elif side == self.LEFT:
            return sideLeft
        else:
            return False # just in case

class Plotter(object):
    # Creates a simple plotting object that goes from point to point.
    # This makes outline drawing easier since calculations only need to be the delta from
    # one point to the next.  The default plotting in reportlab requires both
    # ends of the line in absolute sense.  Thus calculations can become increasingly more
    # complicated given various options.  Using this object simplifies the calculations significantly.

    def __init__(self, canvas, x=0, y=0, cropmarkLength=-1, cropmarkSpacing=-1):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.LEFT, self.RIGHT, self.TOP, self.BOTTOM, self.LINE, self.NO_LINE, self.DOT = range(1, 8) # Constants
        if cropmarkLength < 0:
            cropmarkLength = 0.2
        if cropmarkSpacing < 0:
            cropmarkSpacing = 0.1
        self.CropMarkLength = cropmarkLength  # The length of a cropmark
        self.CropMarkSpacing = cropmarkSpacing # The spacing between the cut point and the start of the cropmark
        self.DotSize = 0.2 #Size of dot marks

    def setXY(self, x, y):
        self.x = x
        self.y = y

    def getXY(self):
        return (self.x, self.y)

    def move(self, delta_x=0, delta_y=0, pen=False):
        if pen is False:
            pen = self.NO_LINE
        x, y = self.getXY() # get current point
        new_x = x + delta_x # calculate new point from delta
        new_y = y + delta_y
        if pen == self.LINE:
            self.canvas.line(x, y, new_x, new_y)
        if pen == self.DOT:
             self.canvas.circle(new_x, new_y, self.DotSize)
        self.setXY(new_x, new_y) # save the new point

    def cropmark(self, enabled, direction):
        # From current point, draw a cropmark in the correct direction and return to starting point
        if enabled:
            x, y = self.getXY() # Saving for later

            if direction == self.TOP:
                self.move(0, self.CropMarkSpacing)
                self.move(0, self.CropMarkLength, self.LINE)
            if direction == self.BOTTOM:
                self.move(0, -self.CropMarkSpacing)
                self.move(0, -self.CropMarkLength, self.LINE)
            if direction == self.RIGHT:
                self.move(self.CropMarkSpacing, 0)
                self.move(self.CropMarkLength, 0, self.LINE)
            if direction == self.LEFT:
                self.move(-self.CropMarkSpacing, 0)
                self.move(-self.CropMarkLength, 0, self.LINE)
            self.setXY(x, y) # Restore to starting point


class PageLayout(object):
    # Calculate the layout for a page given constraints
    # Given that cards/dividers are rectangular, layouts can be either
    # predominantly Horizontal or Vertical.
    #
    #       Vertical Field                           Horizontal Field
    #  +-------------------------------+     +-------------------------------+
    #  | .-----.  extra   .-----.      |     | .-----.-----.   .-----.       |
    #  | | r*c | .  .  .  |num-1|      |     | |  0  |  1  | . | c-1 | .---. |
    #  | .-----.horizontal.-----.      |     | .-----.-----.   .-----. |num| |
    #  | .---.---.               .---. |     |                    .    | -1| |
    #  | | 0 | 1 |               |c-1| |     |       .       .    .    .---. |
    #  | |   |   |  .  .  .  .  .|   | |     |       .  regular   .      e  v|
    #  | .---.---.               .---. |     |       .  horizontal.      x  e|
    #  |                               |     |       .  field     .      t  r|
    #  |     .    regular          .   |     |       .       .    .    .-r-.t|
    #  |     .    vertical         .   |     |                    .    | a |i|
    #  |          field                |     | .-----.-----.   .-----. |   |c|
    #  | .---.---.               .---. |     | |     |     | . |     | .---.a|
    #  | |   |   |               |r*c| |     | .-----.-----.   .-----. |   |l|
    #  | |   |   |  .  .  .  .  .| -1| |     | |     |     | . |r*c-1| |r*c| |
    #  | .---.---.               .---. |     | .-----.-----.   .-----. .---. |
    #  +-------------------------------+     +-------------------------------+
    #    If the top space that is not          If the right space that is not
    #    tall enough to fit a another row      wide enough to fit another column
    #    of vertical cards is tall enough      of horizontal cars is wide enough
    #    to fit a horizontal row, then         to fit a vertical column, then
    #    rotate cards and fill that row.       rotate cards and fill that column.

    # These are values that can be set once and then used by all PageLayout instances
    pageWidth       = 0     # width of the page.  Needs to be set.
    pageHeight      = 0     # height of the page. Needs to be set.
    extraSpacing    = 0     # any extra spacing needed between the normal field of cards and the extra cards
    minMarginH      = 0     # minimum horizontal margin on page
    minMarginV      = 0     # minimum vertical margin on page
    tabHeight       = 0     # the tab height.  Used for interleaving
    tabWidth        = 0     # the tab width.  Used to check if interleaving is possible.
    dividerWidth    = 0     # the divider width.  Used to check if interleaving is possible.
    tabIsHorizontal = True  # When True, tab is on the long side of the divider (horizontal).  False, tab is on the short side (vertical)
    isWrapper       = False # when True, the layout is for wrappers instead of dividers.
    doExtra         = False # when True, will add extra rotated cards if there is space
    doInterleave    = False # when True, will also look at interleaving the tabs of cards in the field

    def __init__(self, width=0, height=0, rotation=0, extraRotation=0, layoutIsHorizontal=True, tryInterleave=False):
        self.width = width                             # divider width (including any tab)
        self.height = height                           # divider height (including any tab)
        self.rotation = rotation                       # rotation value for the field
        self.extraRotation = extraRotation             # rotation value for extra row/column
        self.layoutIsHorizontal = layoutIsHorizontal   # Horizontal if True, Vertical if False
        self.rows = 0                                  # number of rows in the field
        self.columns = 0                               # number of columns in the field
        self.extra = 0                                 # number of extra dividers
        self.marginWidth = 0                           # horizontal margin of usable space (does not include minimum margin)
        self.marginHeight = 0                          # vertical margin of usable space (does not include minimum margin)
        self.horizontalMargin = self.minMarginH        # horizontal margin of page (includes minimum margin)
        self.verticalMargin   = self.minMarginV        # vertical margin of page (includes minimum margin)
        self.leftover = 0                              # the amount of space left over from the side that could include extras
        self.number = 0                                # total number of dividers supported by this layout
        self.tryInterleave = tryInterleave             # whether to try to interleave this layour or not
        self.isInterleaved = False                     # whether this layout is interleaved

        # Now do the calculations
        self.calculate()  # Get the base number that will fit, no interleaving
        if self.tryInterleave:
            non_interleave_number = self.number # Save for comparison
            self.calculate(interleave=True)
            if non_interleave_number >= self.number:
                self.calculate() # It was better with the base number, redo it.

    def calculate(self, interleave=False):
        # Calculate the layout parameters

        # See if we can interleave
        if ( (self.tabWidth > ( self.dividerWidth / 2 )) or not self.doInterleave):
            self.tryInterleave = False  # Interleaving is not possible since tab is too wide
        self.isInterleaved = interleave and self.tryInterleave # Only do interleave if asked and possible

        # Take out minimum margins
        usableWidth  = self.pageWidth  - (2 * self.minMarginH )
        usableHeight = self.pageHeight - (2 * self. minMarginV )

        # First get the field rows and columns
        if not self.isInterleaved:
            self.columns = int(usableWidth // self.width)
            self.rows    = int(usableHeight // self.height)
            field_width  = self.columns * self.width
            field_height = self.rows    * self.height
        else:
            # Figure out if we are interleaving by column (going up)
            # or if we are interleaving by row (going right)
            if ( (self.layoutIsHorizontal and self.tabIsHorizontal) or
                 (not self.layoutIsHorizontal and not self.tabIsHorizontal) or
                 (not self.layoutIsHorizontal and self.isWrapper) ):
               doUpDown = True
            else:
               doUpDown = False

            # see how many dividers of interleaved cards fit in the field
            # Pairs of dividers can be interleaved, then any remaining singles
            if doUpDown:
                # Interleaving going from bottom to top
                doubleHeight = 2 * self.height - self.tabHeight
                doubles = int( usableHeight // doubleHeight )
                singles = int( (usableHeight - (doubles * doubleHeight) ) // self.height)

                self.rows = int (doubles * 2 + singles)
                self.columns = int(usableWidth // self.width)
                field_width  = self.columns * self.width
                field_height = (doubles * doubleHeight) + (singles * self.height)
            else:
                # Interleaving going left to right
                doubleHeight = 2 * self.height - self.tabHeight
                doubles = int( usableWidth // doubleHeight )
                singles = int( (usableWidth - (doubles * doubleHeight) ) // self.height)

                self.columns = int (doubles * 2 + singles)
                self.rows    = int(usableHeight // self.width)
                field_height = self.rows * self.width
                field_width  = (doubles * doubleHeight) + (singles * self.height)

        self.marginHeight = (usableHeight - field_height) / 2
        self.marginWidth  = (usableWidth  - field_width)  / 2

        # Now see if we can fit any "extra" cards on the page
        self.extra  = 0
        extraMargin = 0
        extraLength = 0
        if self.doExtra:
            if self.layoutIsHorizontal:
                # Layout is Horizontal
                self.leftover = usableWidth - field_width - self.extraSpacing
                if self.leftover >= self.height:
                    # There is space to have a rotated divider
                    if self.isInterleaved and (not self.tabIsHorizontal or self.isWrapper):
                        # Can only interleave the extra area if the tabs are vertical (and all wrappers are)
                        doubleWidth = (2 * self.width) - self.tabHeight
                        doubles = int( usableHeight // doubleWidth )
                        singles = int( (usableHeight - (doubles * doubleWidth) ) // self.width)
                        self.extra  = int( 2 * doubles + singles)
                        extraLength = (doubles * doubleWidth) + (singles * self.width)
                        extraMargin = (usableHeight - extraLength ) / 2
                    else:
                        # All non-interleaved cases
                        self.extra = int( usableHeight // self.width )
                        extraLength = self.extra * self.width
                        extraMargin = (usableHeight - extraLength) / 2

                    if self.extra > 0:
                        self.marginHeight = min(self.marginHeight, extraMargin)
                        self.leftover = usableWidth  - field_width - self.height - self.extraSpacing
                        self.marginWidth  = self.leftover / 2

            else:
                # Layout is Vertical
                self.leftover = usableHeight - field_height - self.extraSpacing
                if self.leftover >= self.width:
                    # There is space to have a rotated divider
                    if self.isInterleaved and (not self.tabIsHorizontal or self.isWrapper):
                        # Can only interleave the extra area if the tabs are vertical (and all wrappers are)
                        doubleHeight = (2 * self.height) - self.tabHeight
                        doubles = int( usableWidth // doubleHeight )
                        singles = int( (usableWidth - (doubles * doubleHeight) ) // self.height)
                        self.extra = int( 2 * doubles + singles)
                        extraLength = (doubles * doubleHeight) + (singles * self.height)
                        extraMargin = (usableWidth - extraLength ) / 2
                    else:
                        # All non-interleaved cases
                        self.extra = int( usableWidth // self.height )
                        extraLength = self.extra * self.height
                        extraMargin = (usableWidth - extraLength) / 2

                    if self.extra > 0:
                        self.marginWidth = min(self.marginWidth, extraMargin)
                        self.leftover = usableHeight - field_height - self.width - self.extraSpacing
                        self.marginHeight = self.leftover / 2

        # To make comparisons easier, store the total number of dividors that can be plotted with this layout
        self.number = int((self.rows * self.columns) + self.extra)

        # Provide the full margin values including the provided minimum margin
        self.horizontalMargin = self.marginWidth  + self.minMarginH
        self.verticalMargin   = self.marginHeight + self.minMarginV

        # For debugging
        #if self.isInterleaved:
        #    print "~~~~Interleaved~~~~~~~~~~~~~~~~~~~~~~~~~~"
        #else:
        #    print "~~~~Regular~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
        #print 'usableWidth: %3.2f usableHeight:%3.2f' % (usableWidth, usableHeight)
        #print 'field_width: %3.2f field_height:%3.2f' % (field_width, field_height)
        #print 'columns:     %3.2f rows:        %3.2f' % (self.columns, self.rows)
        #print 'width:       %3.2f height:      %3.2f' % (self.width, self.height)
        #print 'tab:         %3.2f extraspacing %3.2f' % (self.tabHeight, self.extraSpacing)
        #print 'marginWidth: %3.2f marginHeight:%3.2f' % ((usableWidth  - field_width)  / 2, (usableHeight - field_height) / 2)
        #print 'extra:       %3.2f extraMargin: %3.2f' % (self.extra, extraMargin)
        #print 'leftover:    %3.2f extraLength: %3.2f' % (self.leftover, extraLength)
        #print 'marginWidth: %3.2f marginHeight:%3.2f' % (self.horizontalMargin, self.verticalMargin)

        return

    def paginate(self, items=[], pageNumber=0):
        # This returns a single page (list) of items to print.
        # It takes all the CardPlot items for a page, sets up the CardPlot information
        # and returns a list of items ready to print out on a page

        # Make general assignment of items on the page
        page = []
        for i in range(self.number):
            if items and i < len(items):
                page.append(self.setItem(items[i], i, pageNumber))

        if self.isInterleaved:
            # Note: This section makes use of Python's variables pointing to one object.
            #       So items assigned to page are also updated in 'field' and 'extras'.

            # Convert list of items into an 2 dimentinal array for later use
            field = [[None] * self.columns for i in range(self.rows)]
            for row in range(self.rows):
                for column in range(self.columns):
                    i = row*self.columns + column
                    if i < len(items):
                        field[row][column] = items[i]

            # Now save the extra ones
            fieldsize = self.rows * self.columns
            extras = []
            if len(items) > fieldsize:
                for i in range(fieldsize, self.number):
                    extras.append(items[i])

            # Figure out if we are interleaving by column (going up)
            # or if we are interleaving by row (going right)
            if ( (self.layoutIsHorizontal and self.tabIsHorizontal) or
                 (not self.layoutIsHorizontal and not self.tabIsHorizontal) or
                 (not self.layoutIsHorizontal and self.isWrapper) ):
               doUpDown = True
            else:
               doUpDown = False

            interleaveList = []
            if doUpDown:
                for column in range(self.columns):
                    slice = []
                    for row in range(self.rows):
                        if field[row][column] != None:
                            slice.append( field[row][column] )
                    interleaveList.append( slice )
            else:
                for row in range(self.rows):
                    slice = []
                    for column in range(self.columns):
                        if field[row][column] != None:
                            slice.append( field[row][column] )
                    interleaveList.append( slice )

            newHeight = 0
            for swipe in interleaveList:
                delta = self.interleaveList(swipe, doUpDown)
                newHeight = max(newHeight, delta)

            # Adjust the "extra" ones (the leftover items) to be next to interleaved ones
            if extras:
                # Adjust all relative to the rest of the field
                for i in extras:
                    if self.layoutIsHorizontal:
                        i.x = newHeight + self.extraSpacing
                    else:
                        i.y = newHeight + self.extraSpacing

                # Interleave, but only vertical tabed dividers can be interleaved
                if (not self.tabIsHorizontal or self.isWrapper):
                    if self.layoutIsHorizontal:
                        doUpDown = True
                    else:
                        doUpDown = False
                    delta = self.interleaveList(extras, doUpDown)

        return (self.horizontalMargin, self.verticalMargin, page)

    def setItem(self, item, itemOnPage=0, pageNumber=0, dx=0, dy=0):
        # Given a CardPlot object called item, its number on the page, and the page number
        # Return/set the items x,y,rotation, crop mark settings, and page number
        # The primary field is filled up first, row by row, and then the extra area (if any)
        # For x,y assume the canvas has already been adjusted for the margins
        # dx, dy will be used when iterleaving is implemented
        item.page = pageNumber
        if itemOnPage < (self.columns * self.rows):
            # In the main field of the page
            item.rotation = self.rotation
            x = itemOnPage % self.columns
            y = (self.rows - 1) - ( itemOnPage // self.columns )
            item.x = x * self.width + dx
            item.y = y * self.height + dy
            item.cropOnTop = (y == self.rows - 1)
            item.cropOnBottom = (y == 0)
            item.cropOnLeft = (x == 0)
            item.cropOnRight = (x == self.columns - 1)
        else:
            # In the extra area
            item.rotation = self.extraRotation
            e = itemOnPage - (self.columns * self.rows) # e = extra item on page
            if self.layoutIsHorizontal:
                item.x = (self.columns * self.width) + self.extraSpacing + dx
                item.y = e * self.width + dy
                item.cropOnLeft   = True
                item.cropOnRight  = True
                item.CropOnBottom = (e == 0)
                item.CropOnTop    = (e == self.extra - 1)
            else:
                item.x = e * self.height + dx
                item.y = (self.rows * self.height) + self.extraSpacing + dy
                item.cropOnTop    = True
                item.cropOnBottom = True
                item.CropOnLeft   = (e == 0)
                item.CropOnRight  = (e == self.extra - 1)
        return item

    def interleaveList(self, items, isUpDown=True, isPositive=True):
        # Interleave a list of items, all in the same direction
        # This is done by interleaving pairs, then adjusting any remaining singles
        height = 0
        if not items:
            return 0
        if isPositive:
            sign = 1
        else:
            sign = -1

        # Start with location of first item
        x, y = items[0].x, items[0].y
        # But make sure it starts on the edge
        if isUpDown:
            y = 0
        else:
            x = 0

        # First interleave pairs of dividors
        count = len(items)
        while items and count > 1:
            i1 = items.pop(0)
            i2 = items.pop(0)
            count -= 2
            delta = self.interleave(i1, i2, x, y)
            height =+ sign * delta
            if isUpDown:
                y += sign * delta
            else:
                x += sign * delta

        # Now work on leftover singles
        while items:
            i1 = items.pop(0)
            i1.setXY( x, y)
            height =+ sign * i1.height
            if isUpDown:
                y += sign * i1.height
            else:
                x += sign * i1.height

        return height

    def interleave(self,item1, item2, x=None, y=None):
        # Interleave the 2nd card with the 1st card and move 1st card dx,dy
        # Returns the total height of the two cards after any interleaving
        if x is None or y is None:
            pass
        else:
            item1.setXY(x, y)

        # We take our cues on how to interleave from item1
        # So item2 is always placed "on top" of the tab
        # of item1, no matter which way item1 is rotated

        # Get the cards close (but not interleaved) and in the same rotation
        # Why, because we haven't checked to see if we can interleave them.
        # And this at least gets them as close as possible otherwise
        adjustment = self.tabHeight
        if self.isWrapper and (item1.rightSide == item2.rightSide):
            #special case where wrapper tabs will be interleaved
            adjustment = self.tabHeight + min(item1.stackHeight, item2.stackHeight)

        if item1.rotation == 0:
            item2.setXY(item1.x, item1.y + item1.height, item1.rotation)
            interleave_x, interleave_y = 0, -adjustment
        elif item1.rotation == 90:
            item2.setXY(item1.x + item1.height, item1.y, item1.rotation)
            interleave_x, interleave_y = -adjustment, 0
        elif item1.rotation == 180:
            item2.setXY(item1.x, item1.y - item1.height, item1.rotation)
            interleave_x, interleave_y = 0, adjustment
        elif item1.rotation == 270:
            item2.setXY(item1.x - item1.height, item1.y, item1.rotation)
            interleave_x, interleave_y = adjustment, 0
        else:
            item1.setXY(item1.x, item1.y, 0)
            item2.setXY(item1.x, item1.y + item1.height, item1.rotation)
            interleave_x, interleave_y = 0, adjustment

        if item1.isTabCentred or item2.isTabCentred or ( (self.dividerWidth / 2) < self.tabWidth):
            # Can't interleave, so we are done
            return item1.height + item2.height

        # Set the rotation of the 2nd card
        if self.isWrapper:
            if item1.rightSide == item2.rightSide:
                item2.rotate(180)
        else:
            # Normal Dividors
            item2.rotate(180)
            if item1.rightSide != item2.rightSide:
                item2.flipFront2Back()

        # Now interleave
        item2.setXY(item2.x + interleave_x, item2.y + interleave_y)
        return item1.height + item2.height - adjustment

class DividerDrawer(object):
    def __init__(self):
        self.canvas = None

    def draw(self, cards, options):
        self.options = options

        self.registerFonts()
        self.canvas = canvas.Canvas(
            options.outfile,
            pagesize=(options.paperwidth, options.paperheight))
        self.drawDividers(cards)
        self.canvas.save()

    def registerFonts(self):
        try:
            dirn = os.path.join(self.options.data_path, 'fonts')
            self.fontNameRegular = 'MinionPro-Regular'
            pdfmetrics.registerFont(TTFont(self.fontNameRegular, os.path.join(
                dirn, 'MinionPro-Regular.ttf')))
            self.fontNameBold = 'MinionPro-Bold'
            pdfmetrics.registerFont(TTFont(self.fontNameBold, os.path.join(
                dirn, 'MinionPro-Bold.ttf')))
            self.fontNameOblique = 'MinionPro-Oblique'
            pdfmetrics.registerFont(TTFont(self.fontNameOblique, os.path.join(
                dirn, 'MinionPro-It.ttf')))
        except:
            print >> sys.stderr, "Warning, Minion Pro Font ttf file not found! Falling back on Times"
            self.fontNameRegular = 'Times-Roman'
            self.fontNameBold = 'Times-Bold'
            self.fontNameOblique = 'Times-Oblique'

    def wantCentreTab(self, card):
        return (card.isExpansion() and self.options.centre_expansion_dividers) or self.options.tab_side == "centre"

    def drawOutline(self, item, isBack=False):
        # draw outline or cropmarks
        if isBack and not self.options.cropmarks:
            return
        self.canvas.saveState()
        self.canvas.setLineWidth(self.options.linewidth)

        if (item.rightSide and not isBack) or (not item.rightSide and isBack):
            # the tab is on the other side
            self.canvas.translate(self.options.dividerWidth, 0)
            self.canvas.scale(-1, 1)

        plotter = Plotter(self.canvas,
                          cropmarkLength=self.options.cropmarkLength,
                          cropmarkSpacing=self.options.cropmarkSpacing)

        dividerWidth = self.options.dividerWidth
        dividerHeight = self.options.dividerHeight
        dividerBaseHeight = self.options.dividerBaseHeight
        tabLabelWidth = self.options.labelWidth
        notch_height = self.options.notch_height  # thumb notch height
        notch_width1 = self.options.notch_width1  # thumb notch width: top away from tab
        notch_width2 = self.options.notch_width2  # thumb notch width: bottom on side of tab

        theTabHeight = dividerHeight - dividerBaseHeight
        theTabWidth = self.options.labelWidth

        if self.wantCentreTab(item.card):
            side_2_tab = (dividerWidth - theTabWidth) / 2
        else:
            side_2_tab = 0

        nonTabWidth = dividerWidth - tabLabelWidth - side_2_tab

        if item.lineType.lower() == 'line':
            lineType = plotter.LINE
        elif item.lineType.lower() == 'dot':
            lineType = plotter.DOT
        else:
            lineType = plotter.NO_LINE

        intermediatePoint1 = lineType
        intermediatePoint2 = lineType
        intermediatePoint3 = lineType
        intermediatePoint4 = lineType
        intermediatePoint5 = lineType

        if lineType == plotter.DOT:
            intermediatePoint1 = plotter.NO_LINE
        if side_2_tab < 0.01:
            intermediatePoint2 = intermediatePoint1
        if notch_width2 < 0.01:
            intermediatePoint3 = intermediatePoint1
        if notch_width1 < 0.01:
            intermediatePoint4 = intermediatePoint1
        if notch_height < 0.01 or notch_width1 < 0.01:
            intermediatePoint5 = intermediatePoint1

        cropRightEnable  = self.options.cropmarks and item.translateCropmarkEnable(item.RIGHT)
        cropLeftEnable   = self.options.cropmarks and item.translateCropmarkEnable(item.LEFT)
        cropTopEnable    = self.options.cropmarks and item.translateCropmarkEnable(item.TOP)
        cropBottomEnable = self.options.cropmarks and item.translateCropmarkEnable(item.BOTTOM)

        if not self.options.wrapper:
            # Normal Card Outline
            #    |                       |                   |     |
            #  Z-+                      F+-------------------+E    +-Y
            #                            |                   |
            #  H-+-----------------------+                   2-----2-C
            #    |                       G                   D     |
            #    |             Generic Divider                     |
            #    |          Tab Centered or to the Side            |
            #    |                                                 |
            #  A-+-----------------------1-------------------1-----o-B
            #    |                      V|                  W|     |
            #
            plotter.move(0, 0) # to A
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.cropmark( cropBottomEnable, plotter.BOTTOM)
            plotter.move(nonTabWidth, 0, intermediatePoint1) # A to V
            plotter.cropmark( cropBottomEnable, plotter.BOTTOM)
            plotter.move(theTabWidth, 0, intermediatePoint1) # V to W
            plotter.cropmark( cropBottomEnable, plotter.BOTTOM)
            plotter.move(side_2_tab, 0, lineType) # W to B
            plotter.cropmark( cropBottomEnable, plotter.BOTTOM)
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.move(0, dividerBaseHeight, intermediatePoint2) # B to C
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.move(-side_2_tab, 0, intermediatePoint2) # C to D
            plotter.move(0, theTabHeight, lineType) # D to E
            plotter.cropmark( cropTopEnable, plotter.TOP)
            plotter.move(side_2_tab, 0, plotter.NO_LINE) # E to Y
            plotter.cropmark( cropTopEnable, plotter.TOP)
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.move(-side_2_tab, 0, plotter.NO_LINE) # Y to E
            plotter.move(-theTabWidth, 0, lineType) # E to F
            plotter.cropmark( cropTopEnable, plotter.TOP)
            plotter.move(0, -theTabHeight, lineType) # F to G
            plotter.move(-nonTabWidth, 0, lineType) # G to H
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.move(0, theTabHeight, plotter.NO_LINE) # H to Z
            plotter.cropmark( cropTopEnable, plotter.TOP)
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.move(0, -theTabHeight, plotter.NO_LINE) # Z to H
            plotter.move(0, -dividerBaseHeight, lineType) # H to A

        else:
            # Card Wrapper Outline
            notch_width3 = notch_width1  # thumb notch width: bottom away from tab
            stackHeight = item.card.getStackHeight(self.options.thickness)
            body_minus_notches = dividerBaseHeight - (2.0 * notch_height)
            tab_2_notch = dividerWidth - theTabWidth - side_2_tab - notch_width1
            if (tab_2_notch < 0):
                tab_2_notch = dividerWidth - theTabWidth - side_2_tab
                notch_width1 = 0
            #    |       |                     |                   |    |
            # MM-+       +LL                  U+-------------------+T   +-KK
            #                                  |                   |
            #                                 V1...................1S
            #                                  |                   |
            # NN-+      X5---------------------+...................2----2-Q
            #            |                    W                     R   |
            #  Z-+-------5Y                                             1-P
            #    |                                                      |
            #    |                    Generic Wrapper                   |
            #    |                      Normal Side                     |
            #    |                                                      |
            # AA-4-------4BB                                   N3-------3-O
            #            |                                      |
            #    +       1CC...................................M1       +
            #            |                                      |
            #    +       1DD...................................L1       +
            #            |                                      |
            # FF-4-------4EE                                   K3-------3-J
            #    |                                                      |
            #    |                      Reverse Side                    |
            #    |                       rotated 180                    |
            #    |                                                      |
            #  A-+-------5B                                             1-I
            #            |                    D                     G   |
            # GG-+      C5---------------------+                   2----2-H
            #                                  |                   |
            # HH-+       +II                  E+-------------------+F   +-JJ
            #    |       |                     |                   |    |
            plotter.move(0, 0, plotter.NO_LINE) # to HH
            plotter.cropmark( cropBottomEnable, plotter.BOTTOM)
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.move(0, theTabHeight, plotter.NO_LINE) # HH to GG
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.move(0, notch_height, plotter.NO_LINE) # GG to A
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.move(notch_width1, 0, intermediatePoint5)  # A  to B
            plotter.move(0, -notch_height, intermediatePoint5)  # B  to C
            plotter.move(0, -theTabHeight, plotter.NO_LINE) # C to II
            plotter.cropmark( cropBottomEnable, plotter.BOTTOM)
            plotter.move(0, theTabHeight, plotter.NO_LINE) # II to C
            plotter.move(tab_2_notch, 0, intermediatePoint5)  # C  to D
            plotter.move(0, -theTabHeight, lineType)  # D  to E
            plotter.cropmark( cropBottomEnable, plotter.BOTTOM)
            plotter.move(theTabWidth, 0, lineType)  # E  to F
            plotter.cropmark( cropBottomEnable, plotter.BOTTOM)
            plotter.move(0, theTabHeight, intermediatePoint2)  # F  to G
            plotter.move(side_2_tab, 0, intermediatePoint2)  # G  to H
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.move(0, -theTabHeight, plotter.NO_LINE) # H to JJ
            plotter.cropmark( cropBottomEnable, plotter.BOTTOM)
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.move(0, theTabHeight, plotter.NO_LINE) # JJ to H
            plotter.move(0, notch_height, intermediatePoint1)  # H  to I
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.move(0, body_minus_notches, intermediatePoint3)  # I  to J
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.move(-notch_width2, 0, intermediatePoint3)  # J  to K
            plotter.move(0, notch_height, intermediatePoint1)  # K  to L
            plotter.move(0, stackHeight, intermediatePoint1)  # L  to M
            plotter.move(0, notch_height, intermediatePoint3)  # M  to N
            plotter.move(notch_width2, 0, intermediatePoint3)  # N  to O
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.move(0, body_minus_notches, intermediatePoint1)  # O  to P
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.move(0, notch_height, intermediatePoint2)  # P  to Q
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.move(-side_2_tab, 0, intermediatePoint2)  # Q  to R
            plotter.move(0, stackHeight, intermediatePoint1)  # R  to S
            plotter.move(0, theTabHeight, lineType)  # S  to T
            plotter.cropmark( cropTopEnable, plotter.TOP)
            plotter.move(side_2_tab, 0, plotter.NO_LINE) # T to KK
            plotter.cropmark( cropRightEnable, plotter.RIGHT)
            plotter.cropmark( cropTopEnable, plotter.TOP)
            plotter.move(-side_2_tab, 0, plotter.NO_LINE) # KK to T
            plotter.move(-theTabWidth, 0, lineType)  # T  to U
            plotter.cropmark( cropTopEnable, plotter.TOP)
            plotter.move(-tab_2_notch, 0, plotter.NO_LINE)  # U to LL
            plotter.cropmark( cropTopEnable, plotter.TOP)
            plotter.move(tab_2_notch, 0, plotter.NO_LINE)  # LL to U
            plotter.move(0, -theTabHeight, intermediatePoint1)  # U  to V
            plotter.move(0, -stackHeight, lineType)  # V  to W
            plotter.move(-tab_2_notch, 0, intermediatePoint5)  # W  to X
            plotter.move(0, -notch_height, intermediatePoint5)  # X  to Y
            plotter.move(-notch_width1, 0, intermediatePoint5)  # Y  to Z
            plotter.move(0, notch_height, plotter.NO_LINE)  # Z to NN
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.move(0, theTabHeight + stackHeight, plotter.NO_LINE)  # NN to MM
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.cropmark( cropTopEnable, plotter.TOP)
            plotter.move(0, -theTabHeight - stackHeight, plotter.NO_LINE)  # MM to NN
            plotter.move(0, -notch_height, plotter.NO_LINE)  # NN to Z
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.move(0, -body_minus_notches, intermediatePoint4)  # Z  to AA
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.move(notch_width3, 0, intermediatePoint4)  # AA to BB
            plotter.move(0, -notch_height, intermediatePoint1)  # BB to CC
            plotter.move(0, -stackHeight, intermediatePoint1)  # CC to DD
            plotter.move(0, -notch_height, intermediatePoint4)  # DD to EE
            plotter.move(-notch_width3, 0, intermediatePoint4)  # EE to FF
            plotter.cropmark( cropLeftEnable, plotter.LEFT)
            plotter.move(0, -body_minus_notches, lineType) # FF to A

            # Add fold lines
            self.canvas.setStrokeGray(0.9)
            plotter.setXY(dividerWidth - side_2_tab, dividerHeight + stackHeight + dividerBaseHeight ) # to R
            plotter.move(-theTabWidth, 0, plotter.LINE) # R to W
            plotter.move(0, stackHeight) # W to V
            plotter.move(theTabWidth, 0, plotter.LINE) # V to S

            plotter.setXY( notch_width1, dividerHeight ) # to DD
            plotter.move( dividerWidth - notch_width2 - notch_width1, 0, plotter.LINE ) # DD to L
            plotter.move( 0, stackHeight) # L to M
            plotter.move( -dividerWidth + notch_width2 + notch_width1, 0, plotter.LINE ) # M to CC

        self.canvas.restoreState()

    def add_inline_images(self, text, fontsize):
        path = os.path.join(self.options.data_path, 'images')
        replace = '<img src=' "'%s/coin_small_\\1.png'" ' width=%d height=' "'100%%'" ' valign=' "'middle'" '/>'
        replace = replace % (path, fontsize * 1.2)
        text = re.sub('(\d+)\s(c|C)oin(s)?', replace, text)
        replace = '<img src=' "'%s/coin_small_question.png'" ' width=%d height=' "'100%%'" ' valign=' "'middle'" '/>'
        replace = replace % (path, fontsize * 1.2)
        text = re.sub('\?\s(c|C)oin(s)?', replace, text)
        replace = '<img src=' "'%s/coin_small_empty.png'" ' width=%d height=' "'100%%'" ' valign=' "'middle'" '/>'
        replace = replace % (path, fontsize * 1.2)
        text = re.sub('empty\s(c|C)oin(s)?', replace, text)
        replace = '<img src=' "'%s/victory_emblem.png'" ' width=%d height=' "'120%%'" ' valign=' "'middle'" '/>'
        replace = replace % (path, fontsize * 1.5)
        text = re.sub('\<VP\>', replace, text)
        replace = '<img src=' "'%s/debt_\\1.png'" ' width=%d height=' "'105%%'" ' valign=' "'middle'" '/>&thinsp;'
        replace = replace % (path, fontsize * 1.2)
        text = re.sub('(\d+)\sDebt', replace, text)
        replace = '<img src=' "'%s/debt.png'" ' width=%d height=' "'105%%'" ' valign=' "'middle'" '/>&thinsp;'
        replace = replace % (path, fontsize * 1.2)
        text = re.sub('Debt', replace, text)
        replace = '<img src=' "'%s/potion_small.png'" ' width=%d height=' "'100%%'" ' valign=' "'middle'" '/>'
        replace = replace % (path, fontsize * 1.2)
        text = re.sub('Potion', replace, text)
        return text

    def drawCardCount(self, card, x, y, offset=-1):
        if card.count < 1:
            return 0

            # base width is 16 (for image) + 2 (1 pt border on each side)
        width = 18

        cardIconHeight = y + offset
        countHeight = cardIconHeight - 4

        self.canvas.drawImage(
            os.path.join(self.options.data_path, 'images', 'card.png'),
            x,
            countHeight,
            16,
            16,
            preserveAspectRatio=True,
            mask='auto')

        self.canvas.setFont(self.fontNameBold, 10)
        count = str(card.count)
        self.canvas.drawCentredString(x + 8, countHeight + 4, count)
        return width

    def drawCost(self, card, x, y, costOffset=-1):
        # base width is 16 (for image) + 2 (1 pt border on each side)
        width = 18

        costHeight = y + costOffset
        coinHeight = costHeight - 5
        potHeight = y - 3
        potSize = 11

        if card.debtcost:
            self.canvas.drawImage(
                os.path.join(self.options.data_path, 'images', 'debt.png'),
                x,
                coinHeight,
                16,
                16,
                preserveAspectRatio=True,
                mask=[255, 255, 255, 255, 255, 255])
            cost = str(card.debtcost)
            if card.cost != "" and int(card.cost) > 0:
                self.canvas.drawImage(
                    os.path.join(self.options.data_path, 'images',
                                 'coin_small.png'),
                    x + 17,
                    coinHeight,
                    16,
                    16,
                    preserveAspectRatio=True,
                    mask=[255, 255, 255, 255, 255, 255])
                self.canvas.setFont(self.fontNameBold, 12)
                self.canvas.drawCentredString(x + 8 + 17, costHeight,
                                              str(card.cost))
                self.canvas.setFillColorRGB(0, 0, 0)
                width += 16
            self.canvas.setFillColorRGB(1, 1, 1)
        else:
            self.canvas.drawImage(
                os.path.join(self.options.data_path, 'images',
                             'coin_small.png'),
                x,
                coinHeight,
                16,
                16,
                preserveAspectRatio=True,
                mask='auto')
            cost = str(card.cost)
        if card.potcost:
            self.canvas.drawImage(
                os.path.join(self.options.data_path, 'images', 'potion.png'),
                x + 17,
                potHeight,
                potSize,
                potSize,
                preserveAspectRatio=True,
                mask=[255, 255, 255, 255, 255, 255])
            width += potSize

        self.canvas.setFont(self.fontNameBold, 12)
        self.canvas.drawCentredString(x + 8, costHeight, cost)
        self.canvas.setFillColorRGB(0, 0, 0)
        return width

    def drawSetIcon(self, setImage, x, y):
        # set image
        self.canvas.drawImage(
            os.path.join(self.options.data_path, 'images', setImage),
            x,
            y,
            14,
            12,
            mask='auto')

    def nameWidth(self, name, fontSize):
        w = 0
        name_parts = name.split()
        for i, part in enumerate(name_parts):
            if i != 0:
                w += pdfmetrics.stringWidth(' ', self.fontNameRegular,
                                            fontSize)
            w += pdfmetrics.stringWidth(part[0], self.fontNameRegular,
                                        fontSize)
            w += pdfmetrics.stringWidth(part[1:], self.fontNameRegular,
                                        fontSize - 2)
        return w

    def drawTab(self, card, rightSide, wrapper="no"):
        # draw tab flap
        self.canvas.saveState()
        if self.wantCentreTab(card):
            translate_x = self.options.dividerWidth / 2 - self.options.labelWidth / 2
            translate_y = self.options.dividerHeight - self.options.labelHeight
        elif not rightSide:
            translate_x = self.options.dividerWidth - self.options.labelWidth
            translate_y = self.options.dividerHeight - self.options.labelHeight
        else:
            translate_x = 0
            translate_y = self.options.dividerHeight - self.options.labelHeight

        if wrapper == "back":
            translate_y = self.options.labelHeight
            if self.wantCentreTab(card):
                translate_x = self.options.dividerWidth / 2 + self.options.labelWidth / 2
            elif not rightSide:
                translate_x = self.options.dividerWidth
            else:
                translate_x = self.options.labelWidth

        if wrapper == "front":
            translate_y = translate_y + self.options.dividerHeight + 2.0 * card.getStackHeight(
                self.options.thickness)

        self.canvas.translate(translate_x, translate_y)

        if wrapper == "back":
            self.canvas.rotate(180)

        # allow for 3 pt border on each side
        textWidth = self.options.labelWidth - 6
        textHeight = 7
        if self.options.no_tab_artwork:
            textHeight = 4
        textHeight = self.options.labelHeight / 2 - textHeight + \
            card.getType().getTabTextHeightOffset()

        # draw banner
        img = card.getType().getNoCoinTabImageFile()
        if not self.options.no_tab_artwork and img:
            self.canvas.drawImage(
                os.path.join(self.options.data_path, 'images', img),
                1,
                0,
                self.options.labelWidth - 2,
                self.options.labelHeight - 1,
                preserveAspectRatio=False,
                anchor='n',
                mask='auto')

        # draw cost
        if not card.isExpansion() and not card.isBlank(
        ) and not card.isLandmark() and not card.isType('Trash'):
            if 'tab' in self.options.cost:
                textInset = 4
                textInset += self.drawCost(
                    card, textInset, textHeight,
                    card.getType().getTabCostHeightOffset())
            else:
                textInset = 6
        else:
            textInset = 13

        # draw set image
        # always need to offset from right edge, to make sure it stays on
        # banner
        textInsetRight = 6
        if self.options.use_text_set_icon:
            setImageHeight = card.getType().getTabTextHeightOffset()
            setText = card.setTextIcon()
            self.canvas.setFont(self.fontNameOblique, 8)
            if setText is None:
                setText = ""

            self.canvas.drawCentredString(self.options.labelWidth - 10,
                                          textHeight + 2, setText)
            textInsetRight = 15
        else:
            setImage = card.setImage()
            if setImage and 'tab' in self.options.set_icon:
                setImageHeight = 3 + card.getType().getTabTextHeightOffset()

                self.drawSetIcon(setImage, self.options.labelWidth - 20,
                                 setImageHeight)

                textInsetRight = 20

        # draw name
        fontSize = 12
        name = card.name.upper()

        textWidth -= textInset
        textWidth -= textInsetRight

        width = self.nameWidth(name, fontSize)
        while width > textWidth and fontSize > 8:
            fontSize -= .01
            # print 'decreasing font size for tab of',name,'now',fontSize
            width = self.nameWidth(name, fontSize)
        tooLong = width > textWidth
        if tooLong:
            name_lines = name.partition(' / ')
            if name_lines[1]:
                name_lines = (name_lines[0] + ' /', name_lines[2])
            else:
                name_lines = name.split(None, 1)
        else:
            name_lines = [name]
        # if tooLong:
        #    print name

        for linenum, line in enumerate(name_lines):
            h = textHeight
            if tooLong and len(name_lines) > 1:
                if linenum == 0:
                    h += h / 2
                else:
                    h -= h / 2

            words = line.split()
            NotRightEdge = (
                not self.options.tab_name_align == "right" and
                (self.options.tab_name_align == "centre" or rightSide or
                 not self.options.tab_name_align == "edge"))
            if wrapper == "back" and not self.options.tab_name_align == "centre":
                NotRightEdge = not NotRightEdge
            if NotRightEdge:
                if self.options.tab_name_align == "centre":
                    w = self.options.labelWidth / 2 - self.nameWidth(
                        line, fontSize) / 2
                else:
                    w = textInset

                def drawWordPiece(text, fontSize):
                    self.canvas.setFont(self.fontNameRegular, fontSize)
                    if text != ' ':
                        self.canvas.drawString(w, h, text)
                    return pdfmetrics.stringWidth(text, self.fontNameRegular,
                                                  fontSize)

                for i, word in enumerate(words):
                    if i != 0:
                        w += drawWordPiece(' ', fontSize)
                    w += drawWordPiece(word[0], fontSize)
                    w += drawWordPiece(word[1:], fontSize - 2)
            else:
                # align text to the right if tab is on right side, to make
                # tabs easier to read when grouped together extra 3pt is for
                # space between text + set symbol

                w = self.options.labelWidth - textInsetRight - 3
                words.reverse()

                def drawWordPiece(text, fontSize):
                    self.canvas.setFont(self.fontNameRegular, fontSize)
                    if text != ' ':
                        self.canvas.drawRightString(w, h, text)
                    return -pdfmetrics.stringWidth(text, self.fontNameRegular,
                                                   fontSize)

                for i, word in enumerate(words):
                    w += drawWordPiece(word[1:], fontSize - 2)
                    w += drawWordPiece(word[0], fontSize)
                    if i != len(words) - 1:
                        w += drawWordPiece(' ', fontSize)

        if wrapper == "front" and card.getCardCount() >= 5:
            # Print smaller version of name on the top wrapper edge
            self.canvas.translate(0, -card.getStackHeight(
                self.options.thickness))  # move into area used by the wrapper
            fontSize = 8  # use the smallest font
            self.canvas.setFont(self.fontNameRegular, fontSize)

            textHeight = fontSize - 2
            textHeight = card.getStackHeight(
                self.options.thickness) / 2 - textHeight / 2
            h = textHeight
            words = name.split()
            w = self.options.labelWidth / 2 - self.nameWidth(name,
                                                             fontSize) / 2

            def drawWordPiece(text, fontSize):
                self.canvas.setFont(self.fontNameRegular, fontSize)
                if text != ' ':
                    self.canvas.drawString(w, h, text)
                return pdfmetrics.stringWidth(text, self.fontNameRegular,
                                              fontSize)

            for i, word in enumerate(words):
                if i != 0:
                    w += drawWordPiece(' ', fontSize)
                w += drawWordPiece(word[0], fontSize)
                w += drawWordPiece(word[1:], fontSize - 2)

        self.canvas.restoreState()

    def drawText(self, card, divider_text="card", wrapper="no"):

        self.canvas.saveState()
        usedHeight = 0
        totalHeight = self.options.dividerHeight - self.options.labelHeight

        # Figure out if any translation needs to be done
        if wrapper == "back":
            self.canvas.translate(self.options.dividerWidth,
                                  self.options.dividerHeight)
            self.canvas.rotate(180)

        if wrapper == "front":
            self.canvas.translate(0, self.options.dividerHeight +
                                  card.getStackHeight(self.options.thickness))

        if wrapper == "front" or wrapper == "back":
            if self.options.notch_width1 > 0:
                usedHeight += self.options.notch_height

        drewTopIcon = False
        if 'body-top' in self.options.cost and not card.isExpansion():
            self.drawCost(card, cm / 4.0, totalHeight - usedHeight - 0.5 * cm)
            drewTopIcon = True

        Image_x = self.options.dividerWidth - 16
        if 'body-top' in self.options.set_icon and not card.isExpansion():
            setImage = card.setImage()
            if setImage:
                self.drawSetIcon(setImage, Image_x,
                                 totalHeight - usedHeight - 0.5 * cm - 3)
                Image_x -= 16
                drewTopIcon = True

        if self.options.count:
            self.drawCardCount(card, Image_x,
                               totalHeight - usedHeight - 0.5 * cm)
            drewTopIcon = True

        if drewTopIcon:
            usedHeight += 15

        # Figure out what text is to be printed on this divider
        if divider_text == "blank":
            # blank divider, no need to go on
            return
        elif divider_text == "rules":
            # Add the extra rules text to the divider
            if card.extra:
                descriptions = (card.extra, )
            else:
                # Asked for rules and they don't exist, so don't print anything
                return
        elif divider_text == "card":
            # Add the card text to the divider
            descriptions = re.split("\n", card.description)
        else:
            # Don't know what was asked, so don't print anything
            return

        s = getSampleStyleSheet()['BodyText']
        s.fontName = "Times-Roman"
        s.alignment = TA_JUSTIFY

        textHorizontalMargin = .5 * cm
        textVerticalMargin = .3 * cm
        textBoxWidth = self.options.dividerWidth - 2 * textHorizontalMargin
        textBoxHeight = totalHeight - usedHeight - 2 * textVerticalMargin
        spacerHeight = 0.2 * cm
        minSpacerHeight = 0.05 * cm

        while True:
            paragraphs = []
            # this accounts for the spacers we insert between paragraphs
            h = (len(descriptions) - 1) * spacerHeight
            for d in descriptions:
                dmod = self.add_inline_images(d, s.fontSize)
                p = Paragraph(dmod, s)
                h += p.wrap(textBoxWidth, textBoxHeight)[1]
                paragraphs.append(p)

            if h <= textBoxHeight or s.fontSize <= 1 or s.leading <= 1:
                break
            else:
                s.fontSize -= 1
                s.leading -= 1
                spacerHeight = max(spacerHeight - 1, minSpacerHeight)

        h = totalHeight - usedHeight - textVerticalMargin
        for p in paragraphs:
            h -= p.height
            p.drawOn(self.canvas, textHorizontalMargin, h)
            h -= spacerHeight

        self.canvas.restoreState()

    def drawDivider(self, item, isBack=False, horizontalMargin=-1, verticalMargin=-1):
        # First save canvas state
        self.canvas.saveState()

        # Make sure we use the right margins
        if horizontalMargin < 0:
            horizontalMargin = self.options.horizontalMargin
        if verticalMargin < 0:
            verticalMargin = self.options.verticalMargin

        # apply the transforms to get us to the corner of the current card
        self.canvas.resetTransforms()
        pageWidth = self.options.paperwidth - (2 * horizontalMargin)
        self.canvas.translate(horizontalMargin,verticalMargin)
        if isBack:
            self.canvas.translate(self.options.back_offset,
                                  self.options.back_offset_height)
            pageWidth -= 2 * self.options.back_offset

        item.translate(self.canvas, pageWidth, isBack)

        # actual drawing
        if not self.options.tabs_only:
            self.drawOutline(item, isBack)

        if self.options.wrapper:
            wrap = "front"
            isBack = False # Safety.  If a wrapper, there is no backside
        else:
            wrap = "no"

        rightSide = item.rightSide
        cardText  = item.textTypeFront
        if isBack:
            rightSide = not rightSide
            cardText  = item.textTypeBack

        self.drawTab(item.card, rightSide, wrapper=wrap)
        if not self.options.tabs_only:
            self.drawText(item.card, cardText, wrapper=wrap)
            if self.options.wrapper:
                self.drawTab(item.card, rightSide, wrapper="back")
                self.drawText(item.card, item.textTypeBack, wrapper="back")

        # retore the canvas state to the way we found it
        self.canvas.restoreState()

    def drawSetNames(self, pageItems):
        # print sets for this page
        self.canvas.saveState()

        try:
            # calculate the text height, font size, and orientation
            maxFontsize = 12
            minFontsize = 6
            fontname = self.fontNameRegular
            font = pdfmetrics.getFont(fontname)
            fontHeightRelative = (
                font.face.ascent + abs(font.face.descent)) / 1000.0

            canFit = False

            layouts = [{'rotation': 0,
                        'minMarginHeight': self.options.minVerticalMargin,
                        'totalMarginHeight': self.options.verticalMargin,
                        'width': self.options.paperwidth},
                       {'rotation': 90,
                        'minMarginHeight': self.options.minHorizontalMargin,
                        'totalMarginHeight': self.options.horizontalMargin,
                        'width': self.options.paperheight}]

            for layout in layouts:
                availableMargin = layout['totalMarginHeight'] - layout[
                    'minMarginHeight']
                fontsize = availableMargin / fontHeightRelative
                fontsize = min(maxFontsize, fontsize)
                if fontsize >= minFontsize:
                    canFit = True
                    break

            if not canFit:
                import warnings
                warnings.warn("Not enough space to display set names")
                return

            self.canvas.setFont(fontname, fontsize)

            xPos = layout['width'] / 2
            # Place at the very edge of the margin
            yPos = layout['minMarginHeight']

            sets = []
            for item in pageItems:
                setTitle = item.card.cardset.title()
                if setTitle not in sets:
                    sets.append(setTitle)

                # Centered on page
                xPos = layout['width'] / 2
                # Place at the very edge of the margin
                yPos = layout['minMarginHeight']

                if layout['rotation']:
                    self.canvas.rotate(layout['rotation'])
                    yPos = -yPos

            self.canvas.drawCentredString(xPos, yPos, '/'.join(sets))
        finally:
            self.canvas.restoreState()

    def getPageLayout(self, options, maxHeight = -1, tryInterleave = False):

        # set up the PageLayout
        PageLayout.pageWidth       = options.paperwidth
        PageLayout.pageHeight      = options.paperheight
        PageLayout.tabHeight       = options.dividerHeight - options.dividerBaseHeight
        PageLayout.tabWidth        = self.options.labelWidth
        PageLayout.dividerWidth    = options.dividerWidth
        PageLayout.doExtra         = options.optimize_extra
        PageLayout.doInterleave    = options.optimize_interleave
        PageLayout.isWrapper       = options.wrapper
        PageLayout.minMarginH      = options.minHorizontalMargin
        PageLayout.minMarginV      = options.minVerticalMargin
        PageLayout.tabIsHorizontal = options.orientation == "horizontal"
        if options.cropmarks:
            PageLayout.extraSpacing = 2 * ( options.cropmarkLength + options.cropmarkSpacing)

        if maxHeight < 0:
            maxHeight = options.dividerHeightReserved
        else:
            maxHeight = maxHeight
        maxWidth = options.dividerWidthReserved

        layoutIsHorizontal = (options.dividerWidthReserved >= maxHeight )

        # For Horizontal/Vertical, there is a "natural" layout and an "alternate" layout
        # We will be looking at both to see which one fits more cards on a page
        if layoutIsHorizontal:
            # The natural layout for Horizontal Cards
            horizontal = PageLayout(layoutIsHorizontal=True,
                                    width=maxWidth, height=maxHeight, rotation=0, extraRotation=90,
                                    tryInterleave=tryInterleave)
            # The alternate/rotated layout for Horizontal cards
            vertical   = PageLayout(layoutIsHorizontal= False,
                                    width=maxHeight, height=maxWidth, rotation=90, extraRotation=0,
                                    tryInterleave=tryInterleave)
        else:
            # The natural layout for Vertical Cards
            vertical   = PageLayout(layoutIsHorizontal=False,
                                    width=maxWidth, height=maxHeight, rotation=0, extraRotation=90,
                                    tryInterleave=tryInterleave)
            # The alternate/rotated layout for Vertical cards
            horizontal = PageLayout(layoutIsHorizontal=True,
                                    width=maxHeight, height=maxWidth, rotation=90, extraRotation=0,
                                    tryInterleave=tryInterleave)

        # Now pick the layout to use.  A tie goes to the layout with fewest extras
        if layoutIsHorizontal:
            if options.optimize_rotate and (vertical.number == horizontal.number):
                if vertical.extra <  horizontal.extra:
                    layout = vertical
                else:
                    layout = horizontal
            elif options.optimize_rotate and (vertical.number > horizontal.number):
                layout = vertical
            else:
                layout = horizontal
        else:
            if options.optimize_rotate and (horizontal.number == vertical.number):
                if horizontal.extra < vertical.extra:
                    layout = horizontal
                else:
                    layout = vertical
            if options.optimize_rotate and (horizontal.number > vertical.number):
                layout = horizontal
            else:
                layout = vertical

        return layout

    def convert2pages(self, layout, items=[]):
        # Take the layout and all the items and separate the items into pages.
        # Each item will have all its plotting information filled in.
        items = split(items, layout.number) # Note: can be just one page
        pages = []
        for pageNum, pageItems in enumerate(items):
            pages.append(layout.paginate(pageItems, pageNum + 1))
        return pages

    def setupCardPlots(self, options, cards=[]):
        # First, set up common information for the dividers
        # Doing a lot of this up front, while the cards are ordered
        # just in case the dividers need to be reordered on the page.
        # By setting up first, any tab or text flipping will be correct,
        # even if the divider moves around a bit on the pages.

        # Drawing line type
        if options.cropmarks:
            if 'dot' in options.linetype.lower():
                lineType = 'dot' # Allow the DOTs if requested
            else:
                lineType = 'no_line'
        else:
            lineType = options.linetype.lower()

        # Starting with tabs on the left or the right?
        if "right" in options.tab_side:
            tabOnLeft = False # right-alternate, right-alternate-text, right
        else:
            tabOnLeft = True  # left-alternate, left-alternate-text, left, centre, full

        startTabSide = tabOnLeft # Record the starting tab side

        # Set up any alternating tabs and text
        flipTab  = False  # When true, indicates that tabs need to be flipped right/left every other dividor
        flipText = False  # When true, indicates that front/back text needs to be flipped every other dividor

        if "-alternate" in options.tab_side:
            flipTab  = True  # note that this will be true if flipText is True
        if "-alternate-text" in options.tab_side and not options.wrapper:
            flipText = True  # note can't flip wrappers from front to back

        # Now go through all the cards and create their plotter information record...
        items = []
        for card in cards:
            if options.wrapper:
                height = (2 * (options.dividerHeight + card.getStackHeight(options.thickness)) ) + options.verticalBorderSpace
            else:
                height = options.dividerHeightReserved

            item = CardPlot(card,
                            height = height,
                            width = options.dividerWidthReserved,
                            lineType = lineType,
                            rightSide = tabOnLeft,
                            textTypeFront = options.text_front,
                            textTypeBack  = options.text_back,
                            isTabCentred  = self.wantCentreTab(card),
                            stackHeight   = card.getStackHeight(options.thickness)
                           )
            if flipText and (tabOnLeft != startTabSide):
                item.flipFront2Back() # Instead of flipping the tab, flip the whole divider front to back
            items.append(item)
            if flipTab:
                tabOnLeft = not tabOnLeft

        return items

    def drawDividers(self, cards):

        items = self.setupCardPlots(self.options, cards) # Turn cards into items to plot
        layout = self.getPageLayout(self.options, tryInterleave = False) # Get the best "simple" layout that is the same page to page
        self.options.horizontalMargin = layout.horizontalMargin
        self.options.verticalMargin   = layout.verticalMargin
        if not (self.options.wrapper or self.options.optimize_interleave):
            # Normal Dividors and Labels that are the same for every page
            pages = self.convert2pages(layout, items) # now using the layout, turn into pages
        else:
            # Wrappers and interleaved dividers
            minNumber = layout.number # fit at least this many each page
            pages = [] # holds the pages of items
            pageOffset = 1 # Since we are doing this a page at a time, this helps keep track of the page number
            while items:
                # Work on each page, one at a time
                thisLayout = layout # start with default layout
                itemsPage = [] # holds items for this page
                for i in range(minNumber): # Load up the minimum number of items
                    if items:
                        itemsPage.append(items.pop(0))
                maxHeight = max(i.height for i in itemsPage) #Get the tallest
                tryForMore = True
                while tryForMore and items:
                    # see if we can add one more item to page
                    tryHeight = max(maxHeight, items[0].height) # look at next item's height, want tallest

                    # Check to see if any of the dividers has a centre tab
                    # If so, we don't want to interleave, since it throws off the layout calculations
                    hasCenterTab = any(x.isTabCentred == True for x in itemsPage) or items[0].isTabCentred
                    tryInterleave = self.options.optimize_interleave and not hasCenterTab

                    tryLayout = self.getPageLayout(self.options, tryHeight, tryInterleave) # try a new layout
                    if tryLayout.number > thisLayout.number:
                        # It is a better layout
                        tryLayout.number = thisLayout.number + 1 # only +1, since we only looked one ahead
                        if tryLayout.number > (tryLayout.rows * tryLayout.columns):
                            tryLayout.extra = tryLayout.number - ( tryLayout.rows * tryLayout.columns )
                        else:
                            tryLayout.extra = 0
                        thisLayout = tryLayout # Use this for future compares
                        maxHeight = tryHeight
                        itemsPage.append(items.pop(0)) # Add the item to the page
                    else:
                        tryForMore = False
                pages.append(thisLayout.paginate(itemsPage, pageOffset )) # add this one page
                pageOffset += 1
                # Ultimately use the most restrictive margin from all the pages
                self.options.horizontalMargin = min(self.options.horizontalMargin, thisLayout.horizontalMargin)
                self.options.verticalMargin   = min(self.options.verticalMargin,   thisLayout.verticalMargin)

        # Now go page by page and print the dividers
        for pageNum, pageInfo in enumerate(pages):
            hMargin, vMargin, page = pageInfo

            # Front page footer
            if not self.options.no_page_footer and (
                    not self.options.tabs_only and
                    self.options.order != "global"):
                self.drawSetNames(page)

            # Front page
            for item in page:
                self.drawDivider(item, isBack=False, horizontalMargin=hMargin, verticalMargin=vMargin) # print the dividor
            self.canvas.showPage()
            if pageNum + 1 == self.options.num_pages:
                break

            if self.options.tabs_only or self.options.text_back == "none" or self.options.wrapper:
                continue # Don't print the backside of the page

            # back page footer
            if not self.options.no_page_footer and self.options.order != "global":
                self.drawSetNames(page)

            # Back page
            for item in page:
                self.drawDivider(item, isBack=True, horizontalMargin=hMargin, verticalMargin=vMargin) # print the dividor
            self.canvas.showPage()
            if pageNum + 1 == self.options.num_pages:
                break
